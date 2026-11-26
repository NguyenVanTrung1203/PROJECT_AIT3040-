"""Read-only T11 Validation replay; no Test tensors and no artifact writes."""
import json
from datetime import timedelta
from pathlib import Path
import numpy as np
import torch
from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset, timestamp_checks
from src.inference.m5a_wrapper import M5aInference, verify_artifacts
from src.training.engine import severe_qc

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01'


def main():
    torch.use_deterministic_algorithms(True)
    loader = DatasetLoader()
    checksum = checksum_dataset(loader.root, loader.lock)
    timestamp_checks(loader, 'validation')
    split = loader.load_split('validation')
    verify_artifacts(ART)
    saved = np.load(ART / 'validation_predictions.npz', allow_pickle=False)
    results = {}
    for device in ('cpu', 'cuda'):
        if device == 'cuda' and not torch.cuda.is_available():
            continue
        wrapper = M5aInference(ART, device)
        output = np.empty((len(split.X), 15, 2), dtype=np.float64)
        semantic = True
        outputs, verified_checksum = wrapper.predict_validation(loader.root, batch_size=128, allow_fallback=False)
        if verified_checksum != checksum:
            raise ValueError('dataset checksum changed')
        for pred in outputs:
            rows = pred['x_rows']
            ids = tuple(tuple(str(split.vessels.iloc[r]['vessel_id']) for r in pair) for pair in rows)
            semantic &= pred['vessel_ids'] == ids and pred['data_status'] == 'VALID' and pred['qc_status'] == 'PASS' and not pred['fallback_used'] and pred['input_scope'] == 'LOCKED_OFFLINE_VALIDATION'
            output[rows] = pred['forecast_common_en_nm'].cpu().numpy()
        target = np.asarray(saved['anchor_common_EN_nm'])[:,None,:] + np.asarray(saved['target_displacement_nm'],dtype=np.float64)
        err = np.linalg.norm(output-target,axis=-1)
        results[device] = {'array': output, 'ADE':float(err.mean()), 'FDE':float(err[:,-1].mean()), 'severe':int(severe_qc(torch.from_numpy(output),torch.from_numpy(np.asarray(saved['anchor_common_EN_nm']))).sum()), 'semantic':bool(semantic)}
    cpu = results['cpu']; gpu = results.get('cuda')
    report = {'dataset_checksum': checksum, 'encounters':len(split.pairs),'vessels':len(split.X), 'batch_vessels':256, 'torch':str(torch.__version__),'cuda':torch.version.cuda, 'dtype':'model float32; EN projection float64', 'cpu_ade':cpu['ADE'], 'cpu_fde':cpu['FDE'],'cpu_severe':cpu['severe'],'cpu_semantic':cpu['semantic']}
    if gpu:
        diff = np.abs(cpu['array'] - gpu['array'])
        report.update({'gpu_ade':gpu['ADE'],'gpu_fde':gpu['FDE'],'gpu_severe':gpu['severe'],'gpu_semantic':gpu['semantic'], 'max_abs_nm':float(diff.max()),'mean_abs_nm':float(diff.mean()),'p95_abs_nm':float(np.quantile(diff,.95)),'p99_abs_nm':float(np.quantile(diff,.99)), 'vessels_over_5e-5':int((diff.max(axis=(1,2))>5e-5).sum()), 'ade_diff_nm':abs(cpu['ADE']-gpu['ADE']),'fde_diff_nm':abs(cpu['FDE']-gpu['FDE']), 't10_gpu_replay_max_nm':float(np.max(np.abs(gpu['array']-saved['prediction_common_EN_nm']))), 't10_gpu_replay_exact':bool(np.array_equal(gpu['array'],saved['prediction_common_EN_nm']))})
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
