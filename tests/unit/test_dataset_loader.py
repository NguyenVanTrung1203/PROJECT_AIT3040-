import json
import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader

from src.data.dataset_loader import DatasetLoader
from src.data.encounter_dataset import EncounterDataset
from src.data.vessel_dataset import VesselDataset
from src.utils.paths import REPOSITORY_ROOT, resolve_dataset_root


@pytest.fixture(scope='module')
def loader():
    return DatasetLoader()


@pytest.fixture(scope='module')
def train(loader):
    return loader.load_split('train')


@pytest.fixture(scope='module')
def validation(loader):
    return loader.load_split('validation')


def test_resolve_root(monkeypatch):
    monkeypatch.setenv('DATASET_ROOT', 'custom-data')
    assert resolve_dataset_root() == REPOSITORY_ROOT / 'custom-data'
    assert resolve_dataset_root('explicit') == REPOSITORY_ROOT / 'explicit'


def test_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        DatasetLoader(tmp_path / 'absent')


def test_invalid_split(loader):
    with pytest.raises(ValueError, match='Invalid split'):
        loader.load_split('../train')


@pytest.mark.parametrize('version,status,match', [('wrong','READY_AND_LOCKED','version'), ('final_dataset_1.0','OPEN','READY_AND_LOCKED')])
def test_invalid_lock(tmp_path, version, status, match):
    (tmp_path / 'DATASET_LOCK_MANIFEST.json').write_text(json.dumps({'dataset_version':version,'lock_status':status}))
    with pytest.raises(ValueError, match=match):
        DatasetLoader(tmp_path)


def test_lock(loader):
    assert loader.lock['dataset_version'] == 'final_dataset_1.0'
    assert loader.lock['lock_status'] == 'READY_AND_LOCKED'


@pytest.mark.parametrize('name,n,v', [('train',1440,2880),('validation',835,1670)])
def test_split_shapes(loader, name, n, v):
    s = loader.load_split(name)
    assert [a.shape for a in (s.X,s.displacement,s.common,s.anchors,s.labels)] == [(v,10,4),(v,15,2),(n,2,15,2),(n,2,2),(n,)]


def test_vessel_length_and_sample(train):
    ds = VesselDataset(train)
    item = ds[0]
    assert len(ds) == 2880 and item['X'].shape == (10,4) and item['Y'].shape == (15,2)
    assert item['X'].dtype == item['Y'].dtype == torch.float32
    old = float(train.X[0,0,0]); item['X'][0,0] = old + 1
    assert float(train.X[0,0,0]) == old


def test_encounter_length_and_sample(validation):
    ds = EncounterDataset(validation); item = ds[0]
    assert len(ds) == 835
    assert item['model_input']['X'].shape == (2,10,4)
    assert item['model_input']['anchors_EN_nm'].shape == (2,2)
    assert item['model_input']['anchors_EN_nm'].dtype == torch.float64
    assert item['ground_truth']['target_EN_nm'].shape == (2,15,2)
    assert 'label' not in item['model_input'] and 'target_EN_nm' not in item['model_input']


@pytest.mark.parametrize('which', ['train','validation'])
def test_index_mapping(loader, which):
    s = loader.load_split(which)
    for e, (a, b) in enumerate(s.pairs):
        rows = s.vessels.iloc[[a,b]]
        assert rows.vessel.tolist() == ['A','B']
        assert rows.encounter_id.tolist() == [s.encounters.iloc[e].encounter_id] * 2
    i = len(s.encounters) // 2
    assert s.encounter_index(s.encounters.iloc[i].encounter_id) == i
    item = EncounterDataset(s)[i]
    np.testing.assert_array_equal(item['model_input']['X'].numpy(), s.X[s.pairs[i]])
    assert item['vessel_ids'] == s.vessels.iloc[s.pairs[i]].vessel_id.astype(str).tolist()
    with pytest.raises(KeyError):
        s.encounter_index('missing')


def test_reject_bad_vessel_mapping(loader, monkeypatch):
    import pandas as pd
    read_csv = pd.read_csv
    def corrupt(path, *args, **kwargs):
        frame = read_csv(path, *args, **kwargs)
        if str(path).endswith('vessel_tensor_index.csv'):
            frame.loc[0, 'vessel'] = 'B'
        return frame
    monkeypatch.setattr(pd, 'read_csv', corrupt)
    with pytest.raises(ValueError, match='duplicate vessel'):
        loader.load_split('train')


def test_dataloader(train):
    loader = DataLoader(VesselDataset(train), batch_size=256, shuffle=False, drop_last=False, num_workers=0)
    count = 0
    for batch in loader:
        b = batch['X'].shape[0]; count += b
        assert batch['X'].shape == (b,10,4) and batch['Y'].shape == (b,15,2)
        assert torch.isfinite(batch['X']).all() and torch.isfinite(batch['Y']).all()
    assert count == 2880 and b == 64


@pytest.mark.parametrize('kind', [VesselDataset, EncounterDataset])
def test_bad_indices(train, kind):
    ds = kind(train)
    for i in (-1, len(ds)):
        with pytest.raises(IndexError):
            ds[i]
