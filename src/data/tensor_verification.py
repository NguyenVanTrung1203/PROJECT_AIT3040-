"""Read-only contract verification shared by the CLI and analysis notebooks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from src.data.dataset_loader import DatasetLoader
from src.data.encounter_dataset import EncounterDataset

FEATURES = ['own_relative_east_nm', 'own_relative_north_nm', 'east_velocity_kn', 'north_velocity_kn']
RECONSTRUCTION_TOLERANCE_NM = 1e-6  # fixed before checking; matches dataset verifier
ANCHOR_TOLERANCE_NM = 1e-6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum_dataset(root, lock):
    root = Path(root).resolve()
    manifest = root / lock['artifact_checksum_manifest']
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    require(digest == lock['checksums_manifest_sha256'], 'checksum manifest hash mismatch')
    count = 0
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, rel = line.split(None, 1)
        path = (root / rel.strip()).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'invalid checksum path')
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        require(h.hexdigest() == expected, f'checksum mismatch: {rel}')
        count += 1
    require(count == 93, f'unexpected checksum count: {count}')
    return {'status':'PASS','files_verified':count,'manifest_sha256':digest}


def reconstruction_error(s):
    # pairs is derived from the official mapping, not from row ordering.
    restored = s.displacement[s.pairs].astype(np.float64) + s.anchors[:, :, None, :]
    return float(np.max(np.abs(restored - s.common)))


def mutation_tests(s):
    before = EncounterDataset(s)[0]['model_input']
    common = np.array(s.common, copy=True); common[0] += 123
    labels = np.array(s.labels, copy=True); labels[0] = 1 - labels[0]
    metadata = s.metadata.copy(deep=True)
    metadata.loc[0, 'scenario'] = 'changed for isolation test'
    cases = {'future': replace(s, common=common), 'label':replace(s, labels=labels),
             'metadata':replace(s, metadata=metadata)}
    out = {}
    for name, changed in cases.items():
        after = EncounterDataset(changed)[0]['model_input']
        out[name] = set(after) == {'X','anchors_EN_nm'} and all(torch.equal(before[k], after[k]) for k in before)
        require(out[name], f'{name} mutation changed model input')
    return out


def timestamp_checks(loader, name):
    cfg = loader.config['splits'][name]
    path = loader.root / name / 'data' / cfg['data']
    columns = ['encounter_id','vessel','relative_minute','timestamp_utc','anchor_timestamp','is_history','is_future']
    df = pd.read_parquet(path, columns=columns)
    minute = df['relative_minute'].to_numpy()
    delta = (df['timestamp_utc'] - df['anchor_timestamp']).dt.total_seconds().to_numpy()
    require(np.array_equal(delta, minute * 60), f'{name}: timestamp does not align to minute')
    require(np.array_equal(df['is_history'].to_numpy(), minute <= 0), f'{name}: history flags')
    require(np.array_equal(df['is_future'].to_numpy(), minute > 0), f'{name}: future flags')
    groups = df.groupby(['encounter_id','vessel'], observed=True, sort=False)['relative_minute']
    require(groups.size().eq(25).all() and groups.nunique().eq(25).all() and groups.min().eq(-9).all() and groups.max().eq(15).all(), f'{name}: minute coverage')
    require(len(groups) == loader.config['splits'][name]['vessels'], f'{name}: timestamp vessel count')
    require(str(df.timestamp_utc.dt.tz) == 'UTC' and str(df.anchor_timestamp.dt.tz) == 'UTC', f'{name}: timestamps not UTC')
    return {'status':'PASS','rows':len(df),'vessel_groups':len(groups),'utc':True}


def verify(dataset_root=None):
    loader = DatasetLoader(dataset_root)
    checksum = checksum_dataset(loader.root, loader.lock)
    feature = json.loads((loader.root / 'schemas/feature_contract.json').read_text(encoding='utf-8'))
    require(feature['features'] == FEATURES == loader.config['feature_order'], 'feature order mismatch')
    require(loader.config['position_unit'] == 'nautical_mile' and loader.config['velocity_unit'] == 'knot', 'unit mismatch')
    results = {}
    for name in ('train','validation','test'):
        s = loader.load_split(name)  # validates shapes, indices, metadata and labels
        dtype = {key:str(getattr(s,key).dtype) for key in ('X','displacement','common','anchors','labels')}
        require(dtype == {'X':'float32','displacement':'float32','common':'float32','anchors':'float64','labels':'int8'}, f'{name}: dtype mismatch')
        entry = {'shape_index_metadata_label':'PASS', 'dtype':dtype, 'encounters':len(s.encounters),'vessels':len(s.vessels)}
        if name != 'test':
            for key in ('X','displacement','common','anchors','labels'):
                require(np.isfinite(getattr(s,key)).all(), f'{name}: non-finite {key}')
            require(np.all(np.abs(s.X[:,-1,:2]) <= ANCHOR_TOLERANCE_NM), f'{name}: history anchor mismatch')
            error = reconstruction_error(s)
            require(error < RECONSTRUCTION_TOLERANCE_NM, f'{name}: reconstruction error {error}')
            require(np.array_equal(s.metadata['high_risk_label'].to_numpy(), s.labels), f'{name}: metadata labels')
            entry.update({'finite':'PASS','anchor':'PASS','max_reconstruction_error_nm':error,
                          'timestamp':timestamp_checks(loader,name),'mutation':mutation_tests(s)})
        results[name] = entry
    return {'dataset_version':loader.lock['dataset_version'],'lock_status':loader.lock['lock_status'],
            'checksum':checksum,'feature_order':FEATURES,'position_unit':'nm','velocity_unit':'knots',
            'reconstruction_tolerance_nm':RECONSTRUCTION_TOLERANCE_NM,'splits':results,
            'test_scope':'integrity, shape, dtype and index metadata only',
            'limitations':['Loader input isolation does not prove causal integrity of the upstream data pipeline.', 'No Test evaluation, model training or scaler fitting.'],
            'data_readiness':'PASS'}
