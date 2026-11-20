"""Smoke-test the isolated environment with synthetic data and read-only Train access."""
import importlib.metadata as metadata
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

import fastapi
import joblib
import numpy as np
import pandas as pd
import pyarrow
import pydantic
import pytest
import sklearn
import torch
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler


def main():
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / '.env', override=False)
    dataset = Path(os.getenv('DATASET_ROOT', './DATASET_FINAL'))
    if not dataset.is_absolute():
        dataset = root / dataset
    print(f'Python: {platform.python_version()} ({platform.python_implementation()})')
    print(f'Executable: {sys.executable}\nOS: {platform.platform()}')
    for name, module in [('torch', torch), ('numpy', np), ('pandas', pd), ('pyarrow', pyarrow), ('scikit-learn', sklearn), ('joblib', joblib), ('fastapi', fastapi), ('pydantic', pydantic), ('pytest', pytest)]:
        print(f'{name}: {module.__version__}')
    cuda = torch.cuda.is_available()
    print(f'CUDA available: {cuda}; build: {torch.version.cuda}')
    if cuda:
        print(f'CUDA device: {torch.cuda.get_device_name(0)}')
        assert (torch.ones(2, device='cuda') + 1).sum().item() == 4
        torch.cuda.synchronize()
        print('CUDA tensor: PASS')

    array = np.arange(80, dtype=np.float32).reshape(2, 10, 4)
    assert array.shape == (2, 10, 4)
    x = torch.from_numpy(array)
    assert torch.equal(x + 1, torch.tensor(array + 1))
    print('NumPy and Torch tensor: PASS')
    gru = torch.nn.GRU(4, 48, batch_first=True)
    optimizer = torch.optim.Adam(gru.parameters(), lr=0.001)
    output, hidden = gru(x)
    assert output.shape == (2, 10, 48) and hidden.shape == (1, 2, 48)
    print('GRU forward: PASS')
    output.square().mean().backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in gru.parameters())
    print('GRU backward: PASS')
    before = next(gru.parameters()).detach().clone()
    optimizer.step()
    assert not torch.equal(before, next(gru.parameters()).detach())
    print('Optimizer step: PASS')
    with tempfile.TemporaryDirectory(prefix='ait3040_env_') as temp:
        temp = Path(temp)
        torch.save(gru.state_dict(), temp / 'state.pt')
        restored = torch.nn.GRU(4, 48, batch_first=True)
        restored.load_state_dict(torch.load(temp / 'state.pt', map_location='cpu', weights_only=True))
        assert all(torch.equal(a, b) for a, b in zip(gru.parameters(), restored.parameters()))
        scaler = StandardScaler().fit(np.array([[1., 2.], [3., 4.]]))
        expected = scaler.transform([[2., 3.]])
        joblib.dump(scaler, temp / 'scaler.joblib')
        assert np.allclose(joblib.load(temp / 'scaler.joblib').transform([[2., 3.]]), expected)
        frame = pd.DataFrame({'value': [1, 2]})
        frame.to_parquet(temp / 'test.parquet', index=False)
        pd.testing.assert_frame_equal(frame, pd.read_parquet(temp / 'test.parquet'))
    print('State dict, synthetic scaler and Parquet: PASS')
    lock = json.loads((dataset / 'DATASET_LOCK_MANIFEST.json').read_text(encoding='utf-8'))
    assert lock['dataset_version'] == 'final_dataset_1.0' and lock['lock_status'] == 'READY_AND_LOCKED'
    train = pd.read_parquet(dataset / 'train/data/train_1440.parquet')
    x_train = np.load(dataset / 'train/tensors/X_unscaled.npy', mmap_mode='r', allow_pickle=False)
    encounter = pd.read_csv(dataset / 'train/tensors/encounter_tensor_index.csv')
    vessel = pd.read_csv(dataset / 'train/tensors/vessel_tensor_index.csv')
    assert len(train) > 0 and x_train.size > 0 and len(encounter) > 0 and len(vessel) > 0
    print(f'Train read: parquet={train.shape}, tensor={x_train.shape}, encounter_index={encounter.shape}, vessel_index={vessel.shape}: PASS')
    print('FastAPI import and pytest availability: PASS')
    print('ENVIRONMENT SMOKE TEST: PASS')


if __name__ == '__main__':
    main()
