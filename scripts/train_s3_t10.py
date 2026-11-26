"""One auditable T10 run: Train only, Validation selection, never Test."""
import argparse
import csv
import hashlib
import json
import os
import platform
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import sklearn
import torch
import yaml
from torch.utils.data import DataLoader
from src.models.m5a import ResidualGRU
from src.models.pipeline import forecast
from src.models.scalers import TrainOnlyScaler
from src.training.data import VesselTrainingData, fit_verified_train_scalers
from src.training.engine import checkpoint_improved, severe_qc, train_step, validate

BASE = 'f3096fd2d44471ce7bbf455932cd7c3d5634f692'
SEED = 20261110


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def predictions(model, dataset, xs, rs, device):
    """Return predictions in official vessel X_row order, plus immutable mapping."""
    batches = DataLoader(dataset, batch_size=256, shuffle=False, num_workers=0)
    chunks = []
    model.eval()
    with torch.no_grad():
        for batch in batches:
            if any(v != 'validation' for v in batch['split']):
                raise ValueError('predictions require Validation only')
            chunks.append(forecast(model, xs, rs, batch['history'].to(device), batch['anchor'].to(device)).cpu().numpy())
    values = np.concatenate(chunks)
    if values.shape != (len(dataset), 15, 2) or not np.isfinite(values).all():
        raise ValueError('invalid validation predictions')
    return values


def run(root, out, device_name):
    root, out = Path(root).resolve(), Path(out).resolve()
    allowed = (ROOT/'artifacts/checkpoints').resolve()
    if out.exists() or not out.is_relative_to(allowed) or out == allowed:
        raise ValueError('run directory must be new and inside artifacts/checkpoints')
    if not out.name.startswith('s3_t10_'):
        raise ValueError('run directory must identify s3_t10')
    config_path = ROOT/'configs/model_config.yaml'
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    cfg = config['training']
    assert (cfg['optimizer'], cfg['learning_rate'], cfg['weight_decay'], cfg['batch_size'], cfg['min_epochs'], cfg['max_epochs'], cfg['early_stopping_patience'], cfg['gradient_clipping']) == ('AdamW', .0025, .0001, 256, 25, 45, 8, 'none')
    assert cfg['learning_rate_scheduler'] == 'none' and SEED in cfg['seeds']
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True)
    device = torch.device(device_name)
    if device.type == 'cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable')
    loader, splits, checksum, xs, rs = fit_verified_train_scalers(root)
    train, val = VesselTrainingData(splits['train']), VesselTrainingData(splits['validation'])
    assert len(train) == 2880 and len(val) == 1670
    train_batches = DataLoader(train, batch_size=256, shuffle=True, generator=torch.Generator().manual_seed(SEED), drop_last=False, num_workers=0)
    val_batches = DataLoader(val, batch_size=256, shuffle=False, num_workers=0)
    model = ResidualGRU().to(device)
    assert sum(p.numel() for p in model.parameters()) == 15390
    initial = [p.detach().clone() for p in model.parameters()]
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0025, weight_decay=.0001)
    out.mkdir(parents=True, exist_ok=False)
    xs.save(out/'x_scaler.json'); rs.save(out/'residual_scaler.json')
    (out/'run_config.yaml').write_bytes(config_path.read_bytes())
    env = {'python': sys.version, 'platform': platform.platform(), 'torch': str(torch.__version__), 'numpy': np.__version__, 'scikit_learn': sklearn.__version__, 'cuda_version': torch.version.cuda, 'cuda_available': torch.cuda.is_available(), 'device': str(device), 'gpu_name': torch.cuda.get_device_name(device) if device.type == 'cuda' else None, 'gpu_memory_bytes': torch.cuda.get_device_properties(device).total_memory if device.type == 'cuda' else None, 'free_disk_bytes_at_start': shutil.disk_usage(out).free, 'deterministic_algorithms': torch.are_deterministic_algorithms_enabled()}
    save_json(out/'environment.json', env)
    start = datetime.now(timezone.utc).isoformat()
    meta = {'task_id':'AIT3040_S3_T10_FULL_TRAINING', 'run_id':out.name, 'started_utc':start, 'model':'Residual-GRU M5a', 'dataset_version':loader.lock['dataset_version'], 'dataset_manifest_sha256':checksum['manifest_sha256'], 'git_base_commit':BASE, 'runner_sha256':digest(__file__), 'model_config_sha256':digest(config_path), 'seed':SEED, 'device':str(device), 'initialization':'PyTorch default after seed', 'parameter_count':15390, 'mode':'OFFICIAL_TRAINING_CANDIDATE', 'train_encounters':1440, 'validation_encounters':835, 'validation_vessels':1670, 'test_used_for_evaluation':False}
    save_json(out/'run_start.json', meta)
    best = float('inf'); best_epoch = None; best_metrics = None; bad = 0; history = []; stop = 'MAX_EPOCHS'
    try:
        for epoch in range(1, 46):
            t0 = time.monotonic(); records = []; seen = 0
            for batch in train_batches:
                n = len(batch['history']); seen += n
                records.append((n, train_step(model, optimizer, batch, xs, rs, device)))
            if seen != 2880 or len(records) != 12: raise ValueError('Train coverage mismatch')
            before = [p.detach().clone() for p in model.parameters()]
            metrics = validate(model, val_batches, xs, rs, device)
            if any(not torch.equal(a, b) for a,b in zip(before, model.parameters())): raise RuntimeError('validation updated weights')
            expected_sources = {'real_ais_kattegat_v3':590,'augmented_real_ais_kattegat_v3':600,'yanglei':480}
            if metrics['vessels'] != 1670 or {k:v['vessels'] for k,v in metrics['sources'].items()} != expected_sources: raise ValueError('Validation coverage/source mismatch')
            improved = checkpoint_improved(best, metrics['real_ais_ade_nm'], metrics['severe_vessels'])
            if improved:
                best = metrics['real_ais_ade_nm']; best_epoch = epoch; best_metrics = metrics; bad = 0
                torch.save({'artifact_kind':'TRAINING_CANDIDATE', 'model_state':model.state_dict(), 'optimizer_state':optimizer.state_dict(), 'epoch':epoch, 'seed':SEED, 'config':config, 'validation':metrics, 'dataset_version':loader.lock['dataset_version'], 'dataset_manifest_sha256':checksum['manifest_sha256'], 'git_base_commit':BASE, 'runner_sha256':meta['runner_sha256'], 'scalers':{'input':'x_scaler.json','residual':'residual_scaler.json'}}, out/'best_model.pt')
                pred = predictions(model, val, xs, rs, device)
                rows = splits['validation'].vessels
                np.savez_compressed(out/'validation_predictions.npz', prediction_common_EN_nm=pred, target_displacement_nm=np.asarray(splits['validation'].displacement), anchor_common_EN_nm=val.anchors, vessel_id=rows['vessel_id'].astype(str).to_numpy(dtype=str), encounter_id=rows['encounter_id'].astype(str).to_numpy(dtype=str), vessel=rows['vessel'].astype(str).to_numpy(dtype=str), source=val.sources.astype(str), x_row=np.arange(len(val)))
                save_json(out/'validation_metrics.json', metrics)
            else:
                bad += 1
            entry = {'epoch':epoch, 'train_vessels':seen, 'train_batches':len(records), 'loss':{k:sum(n*r[k] for n,r in records)/seen for k in records[0][1] if k != 'gradient_norm'}, 'max_gradient_norm':max(r['gradient_norm'] for _,r in records), 'validation':metrics, 'checkpoint_eligible':improved, 'patience_count':bad, 'duration_seconds':round(time.monotonic()-t0,3)}
            history.append(entry)
            with (out/'training_history.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(entry,ensure_ascii=False,allow_nan=False)+'\n')
            print('EPOCH '+json.dumps(entry,ensure_ascii=False,allow_nan=False),flush=True)
            if epoch >= 25 and bad >= 8: stop = 'EARLY_STOPPING'; break
        if not any(not torch.equal(a,b) for a,b in zip(initial,model.parameters())): raise RuntimeError('model did not update')
        rows = []
        for e in history:
            m = e['validation']; row = {'epoch':e['epoch'],'train_vessels':e['train_vessels'],'train_batches':e['train_batches'],**{'loss_'+k:v for k,v in e['loss'].items()},'max_gradient_norm':e['max_gradient_norm'],'ade_nm':m['ade_nm'],'fde_nm':m['fde_nm'],'real_ais_ade_nm':m['real_ais_ade_nm'],'severe_vessels':m['severe_vessels'],'checkpoint_eligible':e['checkpoint_eligible'],'patience_count':e['patience_count'],'duration_seconds':e['duration_seconds']}
            for source, values in m['sources'].items():
                for key in ('ade_nm','fde_nm','vessels'): row[source+'_'+key] = values[key]
            rows.append(row)
        with (out/'training_history.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        meta.update({'finished_utc':datetime.now(timezone.utc).isoformat(),'epochs_completed':len(history),'early_stopping_status':stop,'best_epoch':best_epoch,'selection_metric':'real_ais_ade_nm_after_projection_and_severe_zero','best_metric':best if best_epoch else None,'best_validation_metrics':best_metrics,'model_selection_status':'CANDIDATE_SELECTED' if best_epoch else 'MODEL_SELECTION_BLOCKED','valid_vessels':1670,'excluded_vessels':0,'exclusion_reason':None,'checkpoint_sha256':digest(out/'best_model.pt') if best_epoch else None,'x_scaler_sha256':digest(out/'x_scaler.json'),'residual_scaler_sha256':digest(out/'residual_scaler.json'),'validation_predictions_sha256':digest(out/'validation_predictions.npz') if best_epoch else None})
        save_json(out/'training_manifest.json',meta)
        files = sorted(p for p in out.iterdir() if p.is_file() and p.name != 'checksums.sha256')
        (out/'checksums.sha256').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files),encoding='utf-8')
        print('COMPLETE '+json.dumps(meta,ensure_ascii=False,allow_nan=False),flush=True)
        if best_epoch is None: raise RuntimeError('MODEL_SELECTION_BLOCKED: no valid checkpoint')
    except Exception as exc:
        save_json(out/'failure.json',{'status':'FAILED','error_type':type(exc).__name__,'error':str(exc),'epochs_completed':len(history),'time_utc':datetime.now(timezone.utc).isoformat()})
        raise


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset-root',required=True); ap.add_argument('--output-dir',required=True)
    ap.add_argument('--device',choices=('cpu','cuda'),required=True)
    args=ap.parse_args(); run(args.dataset_root,args.output_dir,args.device)
