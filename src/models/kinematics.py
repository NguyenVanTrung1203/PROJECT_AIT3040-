"""CV and V4 causal kinematic projection in common East/North coordinates."""
import math
import torch


def _tensor(value, name, shape_tail):
    if not isinstance(value, torch.Tensor) or value.ndim != len(shape_tail) + 1 or tuple(value.shape[1:]) != shape_tail or value.shape[0] == 0:
        raise ValueError(f'{name} must have shape [B,{",".join(map(str, shape_tail))}]')
    if not value.is_floating_point() or not torch.isfinite(value).all():
        raise ValueError(f'{name} must contain finite floating point values')
    return value


def _minutes(minutes, device, dtype):
    expected = torch.arange(1, 16, device=device, dtype=dtype)
    if minutes is None:
        return expected
    actual = torch.as_tensor(minutes, device=device, dtype=dtype)
    if actual.shape != (15,) or not torch.equal(actual, expected):
        raise ValueError('forecast offsets must be exactly +1..+15 minutes')
    return actual


def cv_displacement(anchor_velocity_kn, *, forecast_minutes=None):
    """Return anchor-relative displacement [B,15,2] in nm, not common EN."""
    v = _tensor(anchor_velocity_kn, 'anchor velocity', (2,))
    minutes = _minutes(forecast_minutes, v.device, v.dtype)
    return v[:, None, :] * (minutes[None, :, None] / 60)


def residual_target(target_displacement_nm, cv_displacement_nm):
    y = _tensor(target_displacement_nm, 'target displacement', (15, 2))
    cv = _tensor(cv_displacement_nm, 'CV displacement', (15, 2))
    if y.shape != cv.shape or y.device != cv.device:
        raise ValueError('target and CV must have matching batches and devices')
    return y - cv


def project_forecast(raw_common_nm, anchor_common_nm, anchor_velocity_kn):
    """Apply V4 speed, vector acceleration and conditional heading limits in order.

    Inputs and output use the same floating dtype/device; values must be finite.
    This sequential projection is not a safety certification or a QC substitute.
    """
    raw = _tensor(raw_common_nm, 'forecast', (15, 2))
    anchor = _tensor(anchor_common_nm, 'anchor', (2,))
    vprev = _tensor(anchor_velocity_kn, 'anchor velocity', (2,))
    if raw.shape[0] != anchor.shape[0] or anchor.shape != vprev.shape or any(t.device != raw.device or t.dtype != raw.dtype for t in (anchor, vprev)):
        raise ValueError('projection inputs must share batch, dtype and device')
    prev = anchor
    points = []
    for point in raw.unbind(dim=1):
        desired = (point - prev) * 60
        speed = torch.linalg.vector_norm(desired, dim=-1, keepdim=True)
        desired = desired * (49.999 / speed.clamp_min(1e-12)).clamp(max=1)
        dv = desired - vprev
        change = torch.linalg.vector_norm(dv, dim=-1, keepdim=True)
        desired = vprev + dv * (2.999 / change.clamp_min(1e-12)).clamp(max=1)
        sp = torch.linalg.vector_norm(desired, dim=-1)
        before = torch.linalg.vector_norm(vprev, dim=-1)
        a = torch.atan2(vprev[:, 0], vprev[:, 1])
        b = torch.atan2(desired[:, 0], desired[:, 1])
        delta = torch.remainder(b - a + math.pi, 2 * math.pi) - math.pi
        limit = math.radians(29.9)
        mask = (before >= 3) & (sp >= 3) & (delta.abs() > limit)
        angle = a + delta.clamp(-limit, limit)
        rotated = torch.stack((sp * torch.sin(angle), sp * torch.cos(angle)), dim=-1)
        desired = torch.where(mask[:, None], rotated, desired)
        prev = prev + desired / 60
        points.append(prev)
        vprev = desired
    result = torch.stack(points, dim=1)
    if not torch.isfinite(result).all():
        raise ValueError('nonfinite projected forecast')
    return result
