"""Inference composition only. It never accepts future targets or labels."""
import torch
from .kinematics import _tensor, cv_displacement, project_forecast


def forecast(model, x_scaler, residual_scaler, raw_history, anchors_en_nm, *, forecast_minutes=None):
    """Use unscaled physical history [B,10,4] and own anchor common EN [B,2]."""
    history = _tensor(raw_history, 'raw history', (10, 4))
    anchor = _tensor(anchors_en_nm, 'anchor', (2,))
    if anchor.shape[0] != history.shape[0] or anchor.device != history.device:
        raise ValueError('history and anchors must share batch and device')
    if not torch.all(history[:, -1, :2].abs() <= 1e-6):
        raise ValueError('history position must be relative to its own anchor')
    if x_scaler.kind != 'input' or residual_scaler.kind != 'residual':
        raise ValueError('incorrect scaler kind')
    scaled = x_scaler.transform(history)
    residual = residual_scaler.inverse_transform(model(scaled)).to(dtype=anchor.dtype)
    velocity = history[:, -1, 2:].to(dtype=anchor.dtype)
    raw = anchor[:, None, :] + cv_displacement(velocity, forecast_minutes=forecast_minutes) + residual
    return project_forecast(raw, anchor, velocity)
