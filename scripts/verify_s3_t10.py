"""Independently reload and verify a completed S3 T10 candidate; never evaluate Test."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import torch
from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.training.data import VesselTrainingData, load_verified_data
from src.training.engine import severe_qc
from scripts.train_s3_t10 import digest, predictions, save_json


def run(dataset_root, run_dir):
    out = Path(run_dir).resolve()
    if not out.is_relative_to((ROOT/'artifacts/checkpoints').resolve()) or not out.name.startswith('s3_t10_'):
        raise ValueError('invalid run directory')
    for line in (out/'checksums.sha256').read_text(encoding='utf-8').splitlines():
        expected,name = line.split('  ',1)
        if Path(name).name != name or digest(out/name) != expected: raise ValueError('artifact checksum mismatch: '+name)
    manifest = json.loads((out/'training_manifest.json').read_text(encoding='utf-8'))
    if manifest['model_selection_status'] != 'CANDIDATE_SELECTED': raise ValueError('no valid candidate')
    assert digest(out/'best_model.pt') == manifest['checkpoint_sha256']
    assert digest(out/'x_scaler.json') == manifest['x_scaler_sha256']
    assert digest(out/'residual_scaler.json') == manifest['residual_scaler_sha256']
    assert digest(out/'validation_predictions.npz') == manifest['validation_predictions_sha256']
    checkpoint = torch.load(out/'best_model.pt',map_location='cpu',weights_only=True)
    if checkpoint['artifact_kind'] != 'TRAINING_CANDIDATE' or checkpoint['epoch'] != manifest['best_epoch']:
        raise ValueError('checkpoint provenance mismatch')
    model = ResidualGRU(); model.load_state_dict(checkpoint['model_state'],strict=True); model.eval()
    if sum(p.numel() for p in model.parameters()) != 15390: raise ValueError('parameter count mismatch')
    xs = TrainOnlyScaler.load(out/'x_scaler.json'); rs = TrainOnlyScaler.load(out/'residual_scaler.json')
    if xs.kind != 'input' or rs.kind != 'residual': raise ValueError('scaler kind mismatch')
    loader,splits,checksum = load_verified_data(dataset_root)
    if checksum['manifest_sha256'] != manifest['dataset_manifest_sha256']: raise ValueError('dataset provenance mismatch')
    val=VesselTrainingData(splits['validation'])
    data=np.load(out/'validation_predictions.npz',allow_pickle=False)
    saved=data['prediction_common_EN_nm']; recomputed=predictions(model,val,xs,rs,'cpu')
    max_error=float(np.max(np.abs(saved-recomputed)))
    per_vessel=np.max(np.abs(saved-recomputed),axis=(1,2))
    if not np.isfinite(recomputed).all(): raise ValueError('nonfinite CPU reload prediction')
    if manifest['device'] != 'cuda' or not torch.cuda.is_available(): raise ValueError('original CUDA device is unavailable for exact reproduction')
    torch.use_deterministic_algorithms(True)
    original_device_prediction=predictions(model.cuda(),val,xs,rs,'cuda')
    device_error=float(np.max(np.abs(saved-original_device_prediction)))
    if device_error != 0: raise ValueError('prediction is not exactly reproducible on original device')
    if not np.array_equal(data['x_row'],np.arange(len(val))) or not np.array_equal(data['vessel'],splits['validation'].vessels['vessel'].astype(str).to_numpy()):
        raise ValueError('vessel mapping mismatch')
    if not np.array_equal(data['encounter_id'],splits['validation'].vessels['encounter_id'].astype(str).to_numpy()): raise ValueError('encounter mapping mismatch')
    target=data['target_displacement_nm'].astype(np.float64)+data['anchor_common_EN_nm'][:,None,:]
    error=np.linalg.norm(saved-target,axis=-1)
    if not np.isfinite(error).all(): raise ValueError('nonfinite forecast')
    metrics=manifest['best_validation_metrics']
    if abs(float(error.mean())-metrics['ade_nm']) > 1e-8 or abs(float(error[:,-1].mean())-metrics['fde_nm']) > 1e-8:
        raise ValueError('saved prediction metrics mismatch')
    for source,group in metrics['sources'].items():
        mask=data['source']==source
        if int(mask.sum()) != group['vessels'] or abs(float(error[mask].mean())-group['ade_nm'])>1e-8 or abs(float(error[mask,-1].mean())-group['fde_nm'])>1e-8:
            raise ValueError('source metrics mismatch')
    severe=int(severe_qc(torch.from_numpy(saved),torch.from_numpy(data['anchor_common_EN_nm'])).sum())
    if severe != 0 or severe != metrics['severe_vessels']: raise ValueError('severe QC failure')
    cpu_severe=int(severe_qc(torch.from_numpy(recomputed),torch.from_numpy(data['anchor_common_EN_nm'])).sum())
    if cpu_severe != 0: raise ValueError('CPU reload severe QC failure')
    cpu_error=np.linalg.norm(recomputed-target,axis=-1)
    real=data['source']=='real_ais_kattegat_v3'
    sample=np.asarray(splits['train'].X[:4]); np.testing.assert_allclose(xs.inverse_transform(xs.transform(sample)),sample,rtol=1e-5,atol=1e-5)
    residual=np.asarray(splits['train'].displacement[:4]); np.testing.assert_allclose(rs.inverse_transform(rs.transform(residual)),residual,rtol=1e-5,atol=1e-5)
    result={'status':'PASS_WITH_CPU_PARITY_CAVEAT' if max_error>1e-5 else 'PASS','dataset_checksum_after':checksum,'best_epoch':manifest['best_epoch'],'prediction_shape':list(saved.shape),'reload_device':'cpu','cpu_maximum_difference_nm':max_error,'cpu_diagnostic_threshold_nm':1e-5,'cpu_diagnostic_threshold_status':'FAIL' if max_error>1e-5 else 'PASS','cpu_vessels_over_diagnostic_threshold':int((per_vessel>1e-5).sum()),'cpu_ade_difference_nm':float(cpu_error.mean()-error.mean()),'cpu_fde_difference_nm':float(cpu_error[:,-1].mean()-error[:,-1].mean()),'cpu_real_ais_ade_difference_nm':float(cpu_error[real].mean()-error[real].mean()),'cpu_severe_vessels':cpu_severe,'original_cuda_max_difference_nm':device_error,'original_cuda_exact_match':True,'severe_vessels':severe,'valid_vessels':len(val),'excluded_vessels':0,'verifier_sha256':digest(__file__),'test_used_for_evaluation':False}
    save_json(out/'artifact_verification.json',result)
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='checksums.sha256')
    (out/'checksums.sha256').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--dataset-root',required=True); p.add_argument('--run-dir',required=True); a=p.parse_args(); run(a.dataset_root,a.run_dir)
