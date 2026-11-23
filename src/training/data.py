"""Load verified official splits and derive training-only scaler statistics."""
from pathlib import Path
import numpy as np
import torch
import yaml
from torch.utils.data import Dataset
from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset, timestamp_checks, reconstruction_error
from src.models.kinematics import cv_displacement
from src.models.scalers import TrainOnlyScaler
from scripts.verify_feature_contract import verify_split

LOCKED_CHECKSUM = '21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441'
FEATURES = ['own_relative_east_nm', 'own_relative_north_nm', 'east_velocity_kn', 'north_velocity_kn']


class VesselTrainingData(Dataset):
    def __init__(self, split):
        if split.name not in ('train', 'validation'):
            raise ValueError('only train and validation are permitted')
        self.split = split
        self.anchors = np.empty((len(split.X), 2), dtype=np.float64)
        self.sources = np.empty(len(split.X), dtype=object)
        for i, rows in enumerate(split.pairs):
            self.anchors[rows] = split.anchors[i]
            self.sources[rows] = str(split.metadata.iloc[i]['data_source'])

    def __len__(self):
        return len(self.split.X)

    def __getitem__(self, index):
        s = self.split
        if not 0 <= index < len(self):
            raise IndexError(index)
        return {'history': torch.from_numpy(np.array(s.X[index], dtype=np.float32, copy=True)),
                'target': torch.from_numpy(np.array(s.displacement[index], dtype=np.float32, copy=True)),
                'anchor': torch.from_numpy(self.anchors[index].copy()),
                'source': self.sources[index], 'vessel': str(s.vessels.iloc[index]['vessel']),
                'split': s.name}


def load_verified_data(dataset_root, config_path=None):
    loader = DatasetLoader(dataset_root, config_path)
    canonical = yaml.safe_load((Path(__file__).resolve().parents[2] / 'configs/data_config.yaml').read_text(encoding='utf-8'))
    if loader.config != canonical:
        raise ValueError('data configuration differs from locked repository configuration')
    if loader.lock.get('checksums_manifest_sha256') != LOCKED_CHECKSUM:
        raise ValueError('unrecognized locked dataset checksum manifest')
    checksum = checksum_dataset(loader.root, loader.lock)
    if loader.config['feature_order'] != FEATURES or loader.config['position_unit'] != 'nautical_mile' or loader.config['velocity_unit'] != 'knot':
        raise ValueError('feature order or units differ from contract')
    splits = {}
    for name in ('train', 'validation'):
        split = loader.load_split(name)
        timestamp_checks(loader, name)
        verify_split(loader, name)
        for key in ('X', 'displacement', 'common', 'anchors'):
            if not np.isfinite(getattr(split, key)).all():
                raise ValueError(f'{name}: nonfinite {key}')
        if split.X.dtype != np.float32 or split.displacement.dtype != np.float32 or split.anchors.dtype != np.float64:
            raise ValueError(f'{name}: invalid dtype')
        if np.max(np.abs(split.X[:, -1, :2])) > 1e-6 or reconstruction_error(split) >= 1e-6:
            raise ValueError(f'{name}: anchor/target reconstruction mismatch')
        splits[name] = split
    return loader, splits, checksum


def fit_verified_train_scalers(dataset_root, config_path=None):
    """Fetch Train directly from verified loader; never accept caller-supplied arrays."""
    loader, splits, checksum = load_verified_data(dataset_root, config_path)
    train = splits['train']
    if train.name != 'train':
        raise ValueError('incorrect split provenance')
    x = np.array(train.X, copy=True)
    velocity = torch.from_numpy(x[:, -1, 2:].copy())
    cv = cv_displacement(velocity).numpy()
    residual = np.array(train.displacement, copy=True) - cv
    xs = TrainOnlyScaler('input').fit(x, split='train')
    rs = TrainOnlyScaler('residual').fit(residual, split='train')
    return loader, splits, checksum, xs, rs
