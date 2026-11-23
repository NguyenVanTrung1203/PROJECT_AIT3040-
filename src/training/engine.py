"""Training/validation primitives; no calibration or Test evaluation."""
import math
import numpy as np
import torch
from src.models.pipeline import forecast
from src.training.loss import m5a_loss


def train_step(model, optimizer, batch, xs, rs, device):
    if any(name != 'train' for name in batch['split']):
        raise ValueError('optimizer may consume only verified Train batches')
    x, y = batch['history'].to(device), batch['target'].to(device)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    parts = m5a_loss(model(xs.transform(x)), x, y, rs)
    parts['total'].backward()
    if any(p.grad is None or not torch.isfinite(p.grad).all() for p in model.parameters()):
        raise ValueError('missing or nonfinite gradient; optimizer not stepped')
    grad_norm = torch.linalg.vector_norm(torch.stack([torch.linalg.vector_norm(p.grad.detach().double()) for p in model.parameters()]))
    if not torch.isfinite(grad_norm):
        raise ValueError('nonfinite gradient norm; optimizer not stepped')
    optimizer.step()
    if any(not torch.isfinite(p).all() for p in model.parameters()):
        raise ValueError('nonfinite parameter after optimizer step')
    result = {key: float(value.detach()) for key, value in parts.items()}
    result['gradient_norm'] = float(grad_norm)
    return result


def severe_qc(pred, anchor):
    pos = torch.cat((anchor[:, None, :], pred), dim=1)
    vel = torch.diff(pos, dim=1) * 60
    speed = torch.linalg.vector_norm(vel, dim=-1)
    scalar = torch.diff(speed, dim=1).abs()
    angle = torch.atan2(vel[:, :, 0], vel[:, :, 1])
    delta = (torch.remainder(torch.diff(angle, dim=1) + math.pi, 2 * math.pi) - math.pi).abs()
    moving = (speed[:, :-1] >= 3) & (speed[:, 1:] >= 3)
    return (speed > 50 + 1e-9).any(dim=1) | (scalar > 3 + 1e-9).any(dim=1) | ((delta > math.radians(30 + 1e-9)) & moving).any(dim=1)


def validate(model, batches, xs, rs, device):
    model.eval()
    groups = {}
    severe = 0
    with torch.no_grad():
        for batch in batches:
            if any(name != 'validation' for name in batch['split']):
                raise ValueError('validation accepts only validation batches')
            x, y = batch['history'].to(device), batch['target'].to(device)
            anchor = batch['anchor'].to(device)
            pred = forecast(model, xs, rs, x, anchor)
            truth = anchor[:, None, :] + y.to(anchor.dtype)
            error = torch.linalg.vector_norm(pred - truth, dim=-1)
            if not torch.isfinite(error).all():
                raise ValueError('nonfinite validation metric')
            severe += int(severe_qc(pred, anchor).sum())
            for i, source in enumerate(batch['source']):
                g = groups.setdefault(source, {'sum_ade': 0., 'sum_fde': 0., 'count': 0})
                g['sum_ade'] += float(error[i].mean())
                g['sum_fde'] += float(error[i, -1])
                g['count'] += 1
    count = sum(g['count'] for g in groups.values())
    if not count:
        raise ValueError('empty validation')
    by_source = {s: {'ade_nm': g['sum_ade']/g['count'], 'fde_nm': g['sum_fde']/g['count'], 'vessels': g['count']} for s,g in groups.items()}
    real = [v for k, v in by_source.items() if k in ('real_ais', 'real_ais_kattegat_v3')]
    if not real:
        raise ValueError('Real AIS validation metadata unavailable')
    return {'ade_nm': sum(g['sum_ade'] for g in groups.values())/count,
            'fde_nm': sum(g['sum_fde'] for g in groups.values())/count,
            'real_ais_ade_nm': sum(g['ade_nm']*g['vessels'] for g in real)/sum(g['vessels'] for g in real),
            'severe_vessels': severe, 'sources': by_source, 'vessels': count}


def checkpoint_improved(best, metric, severe):
    if not np.isfinite(metric) or severe < 0:
        raise ValueError('invalid checkpoint metric or QC')
    return severe == 0 and metric < best - 1e-7
