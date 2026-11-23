"""Untrained M5a residual GRU, as specified by the T02 model contract."""
import torch
from torch import nn


class ResidualGRU(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru = nn.GRU(4, 48, num_layers=1, batch_first=True)
        self.head = nn.Sequential(nn.Linear(48, 96), nn.ReLU(), nn.Linear(96, 30))

    def forward(self, scaled_history):
        if not isinstance(scaled_history, torch.Tensor) or scaled_history.ndim != 3 or scaled_history.shape[1:] != (10, 4) or scaled_history.shape[0] == 0:
            raise ValueError('scaled history must have shape [B,10,4], B > 0')
        if not scaled_history.is_floating_point() or not torch.isfinite(scaled_history).all():
            raise ValueError('scaled history must contain finite floating point values')
        _, hidden = self.gru(scaled_history)
        return self.head(hidden[-1]).reshape(-1, 15, 2)
