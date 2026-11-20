from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
import torch

from src.data.dataset_loader import DatasetLoader
from src.data.encounter_dataset import EncounterDataset
from src.data.tensor_verification import FEATURES, RECONSTRUCTION_TOLERANCE_NM, mutation_tests, reconstruction_error


@pytest.fixture(scope='module')
def train():
    return DatasetLoader().load_split('train')


def test_feature_order_and_units():
    cfg = DatasetLoader().config
    assert cfg['feature_order'] == FEATURES
    assert (cfg['position_unit'],cfg['velocity_unit']) == ('nautical_mile','knot')


def test_anchor_relative(train):
    assert np.max(np.abs(train.X[:,-1,:2])) < 1e-6


def test_full_reconstruction_and_mapping(train):
    assert reconstruction_error(train) < RECONSTRUCTION_TOLERANCE_NM
    i = 0
    for side, row in enumerate(train.pairs[i]):
        np.testing.assert_allclose(train.displacement[row].astype('float64') + train.anchors[i,side], train.common[i,side], atol=1e-6, rtol=0)
        assert train.vessels.iloc[row].vessel == 'AB'[side]


def test_reconstruction_detects_changed_target(train):
    changed = np.array(train.common, copy=True); changed[0,0,0,0] += 1
    assert reconstruction_error(replace(train, common=changed)) > RECONSTRUCTION_TOLERANCE_NM


def test_input_isolation_and_mutations(train):
    assert mutation_tests(train) == {'future':True,'label':True,'metadata':True}
    assert set(EncounterDataset(train)[0]['model_input']) == {'X','anchors_EN_nm'}


def test_no_write_through(train):
    assert not train.X.flags.writeable and not train.common.flags.writeable
    old = float(train.X[0,0,0]); sample = EncounterDataset(train)[0]
    sample['model_input']['X'][0,0,0] += 3
    assert float(train.X[0,0,0]) == old
    with pytest.raises(ValueError):
        train.X[0,0,0] = old + 1


def test_index_bounds(train):
    ds = EncounterDataset(train)
    with pytest.raises(IndexError):
        ds[len(ds)]


def test_duplicate_x_row_rejected(monkeypatch):
    read_csv = pd.read_csv
    def corrupt(path, *a, **kw):
        frame = read_csv(path, *a, **kw)
        if str(path).endswith('vessel_tensor_index.csv'):
            frame.loc[1,'X_row'] = frame.loc[0,'X_row']
        return frame
    monkeypatch.setattr(pd, 'read_csv', corrupt)
    with pytest.raises(ValueError, match='invalid vessel X_row'):
        DatasetLoader().load_split('train')
