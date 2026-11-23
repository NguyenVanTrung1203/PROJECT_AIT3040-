"""Train-only channel standardization; caller must supply honest split provenance."""
import json
from pathlib import Path

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler


class TrainOnlyScaler:
    def __init__(self, kind):
        if kind not in ('input', 'residual'):
            raise ValueError('kind must be input or residual')
        self.kind = kind
        self.tail = (10, 4) if kind == 'input' else (15, 2)
        self.mean = None
        self.scale = None

    def _check(self, value):
        if not isinstance(value, (np.ndarray, torch.Tensor)) or value.ndim != 3 or tuple(value.shape[1:]) != self.tail or value.shape[0] == 0:
            raise ValueError(f'{self.kind} values require [B,{self.tail[0]},{self.tail[1]}]')
        if isinstance(value, torch.Tensor):
            if not value.is_floating_point() or not torch.isfinite(value).all():
                raise ValueError('values must be finite floats')
        elif not np.issubdtype(value.dtype, np.floating) or not np.isfinite(value).all():
            raise ValueError('values must be finite floats')

    def fit(self, values, *, split):
        if split != 'train':
            raise ValueError('scaler fitting is restricted to the train split')
        self._check(values)
        values = values.detach().cpu().numpy() if isinstance(values, torch.Tensor) else values
        fitted = StandardScaler().fit(values.reshape(-1, self.tail[-1]))
        self.mean = fitted.mean_.copy()
        self.scale = fitted.scale_.copy() + 1e-6
        return self

    def _apply(self, values, inverse):
        self._check(values)
        if self.mean is None or self.scale is None:
            raise RuntimeError('scaler is not fitted')
        if isinstance(values, torch.Tensor):
            mean = torch.as_tensor(self.mean, device=values.device, dtype=values.dtype)
            scale = torch.as_tensor(self.scale, device=values.device, dtype=values.dtype)
            return values * scale + mean if inverse else ((values - mean) / scale).to(torch.float32)
        result = values * self.scale + self.mean if inverse else (values - self.mean) / self.scale
        return result if inverse else result.astype(np.float32)

    def transform(self, values):
        return self._apply(values, False)

    def inverse_transform(self, values):
        return self._apply(values, True)

    def save(self, path):
        if self.mean is None or self.scale is None:
            raise RuntimeError('scaler is not fitted')
        Path(path).write_text(json.dumps({'version': 1, 'kind': self.kind, 'mean': self.mean.tolist(), 'scale': self.scale.tolist()}, allow_nan=False), encoding='utf-8')

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('version') != 1:
            raise ValueError('unsupported scaler version')
        obj = cls(data['kind'])
        obj.mean = np.asarray(data['mean'], dtype=np.float64)
        obj.scale = np.asarray(data['scale'], dtype=np.float64)
        if obj.mean.shape != (obj.tail[-1],) or obj.scale.shape != obj.mean.shape or not np.isfinite(obj.mean).all() or not np.isfinite(obj.scale).all() or (obj.scale <= 0).any():
            raise ValueError('invalid scaler parameters')
        return obj
