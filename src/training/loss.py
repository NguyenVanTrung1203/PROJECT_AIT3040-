"""Locked M5a objective, evaluated on unprojected displacement."""
import torch
from src.models.kinematics import cv_displacement, residual_target


def m5a_loss(encoded_prediction, history, target_displacement, residual_scaler):
    if encoded_prediction.shape != target_displacement.shape or encoded_prediction.ndim != 3 or encoded_prediction.shape[1:] != (15, 2):
        raise ValueError('predictions and displacement require [B,15,2]')
    if history.shape != (encoded_prediction.shape[0], 10, 4):
        raise ValueError('history requires [B,10,4]')
    if any(not t.is_floating_point() or not torch.isfinite(t).all() for t in (encoded_prediction, history, target_displacement)):
        raise ValueError('loss inputs must be finite floats')
    cv = cv_displacement(history[:, -1, 2:])
    encoded_target = residual_scaler.transform(residual_target(target_displacement, cv))
    predicted = residual_scaler.inverse_transform(encoded_prediction) + cv
    def velocity(p):
        return torch.diff(torch.cat((torch.zeros_like(p[:, :1]), p), dim=1), dim=1) * 60
    vel, true_vel = velocity(predicted), velocity(target_displacement)
    acc, true_acc = torch.diff(vel, dim=1), torch.diff(true_vel, dim=1)
    speed = torch.linalg.vector_norm(vel, dim=-1)
    scalar_delta = torch.abs(torch.diff(speed, dim=1))
    components = {
        'residual': (encoded_prediction - encoded_target).square().mean(),
        'position': (predicted - target_displacement).square().mean(),
        'velocity': ((vel - true_vel) / 10).square().mean(),
        'acceleration': ((acc - true_acc) / 3).square().mean(),
        'penalty': (torch.relu(speed - 50) / 50).square().mean() + (torch.relu(scalar_delta - 3) / 3).square().mean(),
    }
    components['total'] = (components['residual'] + .15 * components['position'] + .02 * components['velocity']
                           + .002 * components['acceleration'] + .001 * components['penalty'])
    if not torch.isfinite(components['total']):
        raise ValueError('nonfinite loss')
    return components
