"""Offline-only, checksum-pinned validation input boundary.

Not a TrackSnapshot or runtime adapter. The trusted entrypoint opens the locked
Validation dataset itself and accepts no caller-created tensors or attestations.
"""
import json
from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd
import torch
import yaml

from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset
from src.training.data import LOCKED_CHECKSUM, FEATURES
from scripts.verify_feature_contract import common_en, velocity_en
from src.inference.m5a_wrapper import EncounterBatch, InferenceError

SOURCE_MAP = {'real_ais_kattegat_v3': 'REAL_AIS',
              'augmented_real_ais_kattegat_v3': 'SYNTHETIC_AIS', 'yanglei': 'YANG_LEI'}
COLUMNS = ['encounter_id', 'vessel', 'vessel_id', 'timestamp_utc', 'anchor_timestamp',
           'relative_minute', 'is_history', 'is_future', 'SOG', 'COG', 'LAT', 'LON',
           'data_source', 'split', 'original_source_timestamp_utc',
           'simulated_source_timestamp_utc', 'source_track_id']


def require(condition, message):
    if not bool(condition):
        raise InferenceError('INVALID_INPUT', message)


def validate_history(s, h):
    """Validate evidence against locked indices and reconstruct X from history only."""
    require(all(c in h.columns for c in COLUMNS), 'missing history metadata')
    n, v = len(s.encounters), len(s.vessels)
    require(n == 835 and v == 1670 and len(h) == v * 10, 'incomplete Validation history')
    require(h.is_history.eq(True).all() and h.is_future.eq(False).all(), 'future in history')
    require(h['split'].eq('validation').all(), 'invalid split')
    require(h.data_source.isin(SOURCE_MAP).all(), 'unknown dataset source')
    require(h[['encounter_id','vessel','vessel_id','data_source','anchor_timestamp',
               'timestamp_utc','relative_minute']].notna().all().all(), 'missing required metadata')
    require(not h.duplicated(['encounter_id', 'vessel', 'relative_minute']).any(), 'duplicate history')
    for col in ('timestamp_utc', 'anchor_timestamp'):
        require(isinstance(h[col].dtype, pd.DatetimeTZDtype) and str(h[col].dt.tz) == 'UTC', 'timestamps must be UTC')
    require((h.timestamp_utc == h.anchor_timestamp + pd.to_timedelta(h.relative_minute, unit='min')).all(), 'history timestamp mismatch')
    require((h.timestamp_utc <= h.anchor_timestamp).all(), 'future timestamp in history')
    require(h.groupby('encounter_id').anchor_timestamp.nunique().eq(1).all(), 'anchor mismatch')
    require(h.groupby('encounter_id').data_source.nunique().eq(1).all(), 'source mismatch')
    expected = s.vessels[['encounter_id', 'vessel', 'vessel_id', 'X_row', 'data_source']]
    h = h.merge(expected, on=['encounter_id', 'vessel'], how='left', validate='many_to_one', suffixes=('', '_index'))
    require(h.X_row.notna().all() and h.vessel_id.eq(h.vessel_id_index).all(), 'identity or mapping mismatch')
    require(h.data_source.eq(h.data_source_index).all(), 'source/index mismatch')
    h = h.sort_values(['X_row','relative_minute'], kind='stable').reset_index(drop=True)
    require(np.array_equal(h.X_row.to_numpy(), np.repeat(np.arange(v), 10)), 'vessel rows mismatch')
    require(np.array_equal(h.relative_minute.to_numpy(), np.tile(np.arange(-9, 1), v)), 'history coverage')
    for pair in s.pairs:
        ids = [s.vessels.iloc[int(i)].vessel_id for i in pair]
        require(all(isinstance(x, str) and x and unicodedata.normalize('NFC', x) == x for x in ids) and ids[0] != ids[1], 'invalid offline vessel identity')
    require(np.array_equal(s.vessels.iloc[s.pairs.ravel()].vessel.to_numpy().reshape(n, 2), np.tile(['A','B'], (n,1))), 'A/B mapping mismatch')
    encounter_ids = s.encounters.encounter_id.astype(str).to_numpy()
    require(np.array_equal(s.vessels.iloc[s.pairs.ravel()].encounter_id.astype(str).to_numpy().reshape(n,2), np.repeat(encounter_ids[:,None],2,axis=1)), 'encounter identity mismatch')
    require(s.metadata.data_source.astype(str).tolist() == h.iloc[np.asarray(s.pairs)[:,0]*10].data_source.tolist(), 'encounter source mismatch')
    require(s.metadata.anchor_timestamp.tolist() == h.iloc[np.asarray(s.pairs)[:,0]*10].anchor_timestamp.tolist(), 'encounter anchor mismatch')
    for source, g in h.groupby('data_source'):
        if source == 'yanglei':
            require(g.original_source_timestamp_utc.isna().all() and g.simulated_source_timestamp_utc.isna().all(), 'Yang Lei must not invent AIS source timestamp')
        else:
            col = 'original_source_timestamp_utc' if source == 'real_ais_kattegat_v3' else 'simulated_source_timestamp_utc'
            require(g[col].notna().all() and g.source_track_id.notna().all(), 'missing source evidence')
            require(isinstance(g[col].dtype, pd.DatetimeTZDtype) and str(g[col].dt.tz) == 'UTC', 'source timestamp must be UTC')
            age = (g.timestamp_utc - g[col]).dt.total_seconds()
            require(age.between(0,60,inclusive='both').all(), 'source timestamp invalid or stale')
            if source == 'augmented_real_ais_kattegat_v3':
                require(g.original_source_timestamp_utc.notna().all(), 'missing original synthetic provenance')
    vals = h[['LAT','LON','SOG','COG']].to_numpy(dtype=np.float64).reshape(v,10,4)
    require(np.isfinite(vals).all() and (abs(vals[:,:,0]) <= 90).all() and (abs(vals[:,:,1]) <= 180).all(), 'invalid coordinates')
    require(((vals[:,:,2] >= 0) & (vals[:,:,2] <= 50) & (vals[:,:,3] >= 0) & (vals[:,:,3] < 360)).all(), 'invalid SOG/COG')
    require(s.X.dtype == np.float32 and s.anchors.dtype == np.float64 and np.isfinite(s.X).all() and np.isfinite(s.anchors).all(), 'invalid tensor dtype or values')
    require(np.max(np.abs(velocity_en(vals[:,:,2],vals[:,:,3])-s.X[:,:,2:])) < 1e-5, 'feature velocity mismatch')
    coords=vals[s.pairs,:,:2]; lat0=coords[:,0,0,0][:,None,None]; lon0=coords[:,0,0,1][:,None,None]
    require((abs(coords[:,:,:,1]-lon0)<180).all(), 'unsupported longitude wrap')
    en=common_en(coords[:,:,:,0],coords[:,:,:,1],lat0,lon0)
    require(np.max(np.abs(en[:,:,9,:]-s.anchors)) < 1e-10, 'anchor frame mismatch')
    require(np.max(np.abs(en-en[:,:,9:10,:]-s.X[s.pairs][:,:,:,:2])) < 1e-6, 'feature frame mismatch')
    return h


def load_validation(dataset_root):
    """Open and verify the fixed Validation data; no caller data is accepted."""
    try:
        loader = DatasetLoader(dataset_root)
        repo = Path(__file__).resolve().parents[2]
        canonical = yaml.safe_load((repo/'configs/data_config.yaml').read_text(encoding='utf-8'))
        require(loader.config == canonical and loader.config['feature_order'] == FEATURES, 'dataset config mismatch')
        require(loader.lock.get('dataset_version') == 'final_dataset_1.0' and loader.lock.get('checksums_manifest_sha256') == LOCKED_CHECKSUM, 'dataset lock mismatch')
        checksum = checksum_dataset(loader.root, loader.lock)
        feature = json.loads((loader.root/'schemas/feature_contract.json').read_text(encoding='utf-8'))
        require(feature['features'] == FEATURES, 'locked feature ordering mismatch')
        s = loader.load_split('validation')
        h = pd.read_parquet(loader.root/'validation'/'data'/loader.config['splits']['validation']['data'], columns=COLUMNS, filters=[('is_history','==',True)])
        h = validate_history(s,h)
        return s,h,checksum
    except InferenceError:
        raise
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise InferenceError('INVALID_INPUT', str(exc)) from exc


def make_batch(s, h, start, stop):
    rows=s.pairs[start:stop]
    anchors=tuple(t.to_pydatetime() for t in s.metadata.anchor_timestamp.iloc[start:stop])
    histories=tuple(tuple(t.to_pydatetime() for t in h.iloc[int(pair[0])*10:int(pair[0])*10+10].timestamp_utc) for pair in rows)
    ids=tuple(tuple(str(s.vessels.iloc[int(r)].vessel_id) for r in pair) for pair in rows)
    sources=tuple(SOURCE_MAP[x] for x in s.metadata.data_source.iloc[start:stop])
    return EncounterBatch(torch.from_numpy(np.array(s.X[rows],copy=True)), torch.from_numpy(np.array(s.anchors[start:stop],copy=True)), ids, anchors, histories, sources, False, False)
