"""Read locked tensors and validate their official index mappings."""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

from src.utils.paths import REPOSITORY_ROOT, resolve_dataset_root


@dataclass
class SplitData:
    name: str
    X: np.ndarray
    displacement: np.ndarray
    common: np.ndarray
    anchors: np.ndarray
    labels: np.ndarray
    metadata: pd.DataFrame
    encounters: pd.DataFrame
    vessels: pd.DataFrame
    pairs: np.ndarray
    records: int

    def encounter_index(self, encounter_id):
        matches = np.flatnonzero(self.encounters['encounter_id'].to_numpy() == encounter_id)
        if len(matches) != 1:
            raise KeyError(encounter_id)
        return int(matches[0])


class DatasetLoader:
    def __init__(self, dataset_root=None, config_path=None):
        path = Path(config_path) if config_path is not None else REPOSITORY_ROOT / 'configs/data_config.yaml'
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        self.config = yaml.safe_load(path.read_text(encoding='utf-8'))
        self.root = resolve_dataset_root(dataset_root, self.config['dataset_root'])
        if not self.root.is_dir():
            raise FileNotFoundError(f'Dataset directory not found: {self.root}')
        self.lock = json.loads((self.root / self.config['lock_manifest']).read_text(encoding='utf-8'))
        if self.lock.get('dataset_version') != self.config['dataset_version']:
            raise ValueError('Dataset version mismatch')
        if self.lock.get('lock_status') != 'READY_AND_LOCKED':
            raise ValueError('Dataset is not READY_AND_LOCKED')

    def load_split(self, name):
        if name not in self.config['splits']:
            raise ValueError(f'Invalid split: {name}')
        cfg = self.config['splits'][name]
        if self.lock['splits'].get(name) != cfg['encounters']:
            raise ValueError(f'{name}: lock split count mismatch')
        path = self.root / name
        arrays = {key: np.load(path / 'tensors' / filename, mmap_mode='r', allow_pickle=False)
                  for key, filename in {'X':'X_unscaled.npy', 'displacement':'target_GRU_displacement_nm.npy',
                      'common':'target_EN_nm.npy', 'anchors':'anchor_positions_EN_nm.npy', 'labels':'labels.npy'}.items()}
        n, v = cfg['encounters'], cfg['vessels']
        h, f, t, o = (self.config[k] for k in ('history_length','input_features','forecast_horizon','output_dimensions'))
        shapes = {'X':(v,h,f), 'displacement':(v,t,o), 'common':(n,2,t,o), 'anchors':(n,2,o), 'labels':(n,)}
        for key, shape in shapes.items():
            a = arrays[key]
            expected_kind = 'iu' if key == 'labels' else 'f'
            if a.shape != shape or a.dtype.kind not in expected_kind:
                raise ValueError(f'{name}: invalid {key} shape or dtype: {a.shape}, {a.dtype}')
        meta = pd.read_parquet(path / 'data/encounter_metadata.parquet')
        ei = pd.read_csv(path / 'tensors/encounter_tensor_index.csv', dtype={'encounter_id':str})
        vi = pd.read_csv(path / 'tensors/vessel_tensor_index.csv', dtype={'encounter_id':str, 'vessel_id':str})
        records = pq.ParquetFile(path / 'data' / cfg['data']).metadata.num_rows
        if records != cfg['records'] or len(meta) != n or len(ei) != n or len(vi) != v:
            raise ValueError(f'{name}: invalid record or index counts')
        if not np.array_equal(ei['encounter_index'].to_numpy(), np.arange(n)) or ei['encounter_id'].duplicated().any():
            raise ValueError(f'{name}: invalid encounter tensor index')
        if meta['encounter_id'].astype(str).tolist() != ei['encounter_id'].tolist():
            raise ValueError(f'{name}: metadata and encounter index mismatch')
        if not np.array_equal(ei['high_risk_label'].to_numpy(), arrays['labels']):
            raise ValueError(f'{name}: label and encounter index mismatch')
        if vi['X_row'].duplicated().any() or set(vi['X_row']) != set(range(v)):
            raise ValueError(f'{name}: invalid vessel X_row index')
        pairs = np.full((n, 2), -1, dtype=np.int64)
        for row in vi.itertuples(index=False):
            e, x = int(row.encounter_index), int(row.X_row)
            if e < 0 or e >= n or row.vessel not in ('A', 'B') or row.encounter_id != ei.iloc[e]['encounter_id']:
                raise ValueError(f'{name}: vessel/encounter index mismatch')
            slot = 0 if row.vessel == 'A' else 1
            if pairs[e, slot] != -1:
                raise ValueError(f'{name}: duplicate vessel in encounter')
            pairs[e, slot] = x
        if (pairs < 0).any():
            raise ValueError(f'{name}: missing vessel A or B')
        vi = vi.set_index('X_row', drop=False).loc[np.arange(v)].reset_index(drop=True)
        return SplitData(name=name, metadata=meta, encounters=ei, vessels=vi, pairs=pairs, records=records, **arrays)
