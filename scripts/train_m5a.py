"""Explicit smoke or training CLI. No mode is selected by default."""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader
from src.models.m5a import ResidualGRU
from src.training.data import VesselTrainingData, fit_verified_train_scalers
from src.training.engine import checkpoint_improved, train_step, validate


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--smoke', action='store_true', help='one epoch; bounded Train batches; artifacts marked SMOKE_ONLY')
    mode.add_argument('--train', action='store_true', help='explicit training mode with locked epoch/selection rules')
    p.add_argument('--dataset-root', required=True)
    p.add_argument('--config', default=str(ROOT/'configs/model_config.yaml'))
    p.add_argument('--data-config', default=str(ROOT/'configs/data_config.yaml'))
    p.add_argument('--seed', type=int, default=20261110)
    p.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    p.add_argument('--output-dir', required=True, help='new directory inside artifacts/checkpoints')
    p.add_argument('--smoke-batches', type=int, default=2)
    return p


def run(args):
    config = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    if config != yaml.safe_load((ROOT/'configs/model_config.yaml').read_text(encoding='utf-8')):
        raise ValueError('config differs from locked repository configuration')
    model_cfg, train_cfg, scale_cfg = config['model'], config['training'], config['scaling']
    required = (model_cfg['input_size'], model_cfg['hidden_size'], model_cfg['num_layers'], model_cfg['fc_hidden_size'], model_cfg['output_size'], model_cfg['forecast_horizon'], model_cfg['output_dimensions'], train_cfg['optimizer'], train_cfg['learning_rate'], train_cfg['weight_decay'], train_cfg['batch_size'], train_cfg['min_epochs'], train_cfg['max_epochs'], train_cfg['early_stopping_patience'], scale_cfg['fit_split'], scale_cfg['scale_epsilon_after_fit'])
    if required != (4, 48, 1, 96, 30, 15, 2, 'AdamW', .0025, .0001, 256, 25, 45, 8, 'train', 1e-6):
        raise ValueError('config differs from locked T02 protocol')
    if args.seed not in train_cfg['seeds'] or args.smoke_batches < 1 or args.smoke_batches > 10:
        raise ValueError('seed or smoke batch limit outside approved range')
    base = (ROOT/'artifacts/checkpoints').resolve()
    out = Path(args.output_dir).resolve()
    if not out.is_relative_to(base) or out == base or out.exists():
        raise ValueError('output must be a new directory inside artifacts/checkpoints')
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    torch.use_deterministic_algorithms(True)
    device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA requested but unavailable')
    loader, splits, checksum, xs, rs = fit_verified_train_scalers(args.dataset_root, args.data_config)
    train_data, val_data = VesselTrainingData(splits['train']), VesselTrainingData(splits['validation'])
    generator = torch.Generator().manual_seed(args.seed)
    train_batches = DataLoader(train_data, batch_size=256, shuffle=True, generator=generator, drop_last=False, num_workers=0)
    val_batches = DataLoader(val_data, batch_size=256, shuffle=False, num_workers=0)
    model = ResidualGRU().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0025, weight_decay=.0001)
    initial = [p.detach().clone() for p in model.parameters()]
    out.mkdir(parents=True, exist_ok=False)
    xs.save(out/'x_scaler.json'); rs.save(out/'residual_scaler.json')
    best = float('inf'); bad = 0; logs = []; checkpoint = None
    epochs = 1 if args.smoke else 45
    for epoch in range(1, epochs + 1):
        records = []
        for i, batch in enumerate(train_batches):
            if args.smoke and i >= args.smoke_batches:
                break
            records.append((len(batch['history']), train_step(model, optimizer, batch, xs, rs, device)))
        before_val = [p.detach().clone() for p in model.parameters()]
        metrics = validate(model, val_batches, xs, rs, device)
        if any(not torch.equal(a, b) for a, b in zip(before_val, model.parameters())):
            raise RuntimeError('validation changed model weights')
        improved = checkpoint_improved(best, metrics['real_ais_ade_nm'], metrics['severe_vessels'])
        if improved:
            best = metrics['real_ais_ade_nm']; bad = 0
        else:
            bad += 1
        total_samples = sum(n for n, _ in records)
        entry = {'epoch': epoch, 'train_batches': len(records), 'loss': {k: sum(n*r[k] for n, r in records)/total_samples for k in records[0][1] if k != 'gradient_norm'}, 'max_gradient_norm': max(r['gradient_norm'] for _, r in records), 'validation': metrics, 'checkpoint_eligible': improved}
        logs.append(entry)
        if args.smoke or improved:
            checkpoint = out/('SMOKE_ONLY.pt' if args.smoke else 'best.pt')
            torch.save({'artifact_kind': 'SMOKE_ONLY' if args.smoke else 'TRAINING_CANDIDATE', 'model_state': model.state_dict(), 'optimizer_state': optimizer.state_dict(), 'config': config, 'seed': args.seed, 'epoch': epoch, 'validation': metrics, 'dataset_version': loader.lock['dataset_version'], 'dataset_manifest_sha256': checksum['manifest_sha256'], 'scalers': {'input': 'x_scaler.json', 'residual': 'residual_scaler.json'}}, checkpoint)
        if not args.smoke and epoch >= 25 and bad >= 8:
            break
    changed = any(not torch.equal(a, b) for a, b in zip(initial, model.parameters()))
    if not changed:
        raise RuntimeError('optimizer did not change model parameters')
    if args.smoke:
        restored = torch.load(checkpoint, map_location=device, weights_only=True)
        if restored['artifact_kind'] != 'SMOKE_ONLY' or any(not torch.equal(restored['model_state'][k], v) for k,v in model.state_dict().items()):
            raise RuntimeError('smoke checkpoint roundtrip failed')
        restored_model = ResidualGRU().to(device)
        restored_model.load_state_dict(restored['model_state'])
        restored_optimizer = torch.optim.AdamW(restored_model.parameters(), lr=.0025, weight_decay=.0001)
        restored_optimizer.load_state_dict(restored['optimizer_state'])
        if any(not torch.equal(restored_model.state_dict()[k], v) for k, v in model.state_dict().items()) or len(restored_optimizer.state) != len(optimizer.state):
            raise RuntimeError('smoke checkpoint restore failed')
        from src.models.scalers import TrainOnlyScaler
        for kind, original, name in (('input', xs, 'x_scaler.json'), ('residual', rs, 'residual_scaler.json')):
            loaded = TrainOnlyScaler.load(out/name)
            if loaded.kind != kind or not np.array_equal(loaded.mean, original.mean) or not np.array_equal(loaded.scale, original.scale):
                raise RuntimeError('scaler roundtrip failed')
    result = {'mode': 'SMOKE_ONLY' if args.smoke else 'TRAINING', 'seed': args.seed, 'device': str(device), 'dataset_version': loader.lock['dataset_version'], 'checksum': checksum, 'parameter_update': changed, 'checkpoint': str(checkpoint) if checkpoint else None, 'epochs': logs}
    (out/'run.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result


def main(argv=None):
    result = run(parser().parse_args(argv))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
