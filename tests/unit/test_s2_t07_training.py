import copy
import importlib.util
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch
from torch.utils.data import DataLoader

from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.training.data import VesselTrainingData, fit_verified_train_scalers
from src.training.engine import checkpoint_improved, severe_qc, train_step, validate
from src.training.loss import m5a_loss


def sample_split(name='train'):
    x = np.zeros((4, 10, 4), np.float32); x[:, :, 2] = 2
    pairs = np.array([[2, 0], [3, 1]])
    return SimpleNamespace(name=name, X=x, displacement=np.zeros((4,15,2),np.float32),
                           pairs=pairs, anchors=np.array([[[1.,2.],[3.,4.]],[[5.,6.],[7.,8.]]]),
                           metadata=pd.DataFrame({'data_source':['real_ais_kattegat_v3','yang_lei']}),
                           vessels=pd.DataFrame({'vessel':['B','B','A','A']}))


def scalers():
    return (TrainOnlyScaler('input').fit(np.zeros((2,10,4),np.float32),split='train'),
            TrainOnlyScaler('residual').fit(np.zeros((2,15,2),np.float32),split='train'))


def test_vessel_mapping_and_split():
    ds = VesselTrainingData(sample_split())
    assert ds[2]['anchor'].tolist() == [1., 2.] and ds[0]['anchor'].tolist() == [3., 4.]
    assert ds[2]['vessel'] == 'A' and ds[0]['vessel'] == 'B'
    assert ds[2]['source'] == 'real_ais_kattegat_v3'
    assert set(ds[0]) == {'history','target','anchor','source','vessel','split'}
    with pytest.raises(ValueError): VesselTrainingData(sample_split('test'))


def test_fit_guard_does_not_accept_arrays(monkeypatch):
    import src.training.data as data
    train, val = sample_split(), sample_split('validation')
    monkeypatch.setattr(data, 'load_verified_data', lambda *a: (None, {'train': val, 'validation': val}, {}))
    with pytest.raises(ValueError, match='provenance'):
        fit_verified_train_scalers('unused')
    monkeypatch.setattr(data, 'load_verified_data', lambda *a: (None, {'train': train, 'validation': val}, {}))
    _, _, _, xs, rs = fit_verified_train_scalers('unused')
    assert xs.mean.shape == (4,) and rs.mean.shape == (2,)
    before = xs.mean.copy(); xs.transform(val.X); np.testing.assert_array_equal(xs.mean, before)


def test_loss_components_hand_calculated_and_gradient():
    _, rs = scalers()
    rs.mean = np.zeros(2); rs.scale = np.ones(2)
    x = torch.zeros((1,10,4)); true = torch.zeros((1,15,2))
    predicted = torch.full((1,15,2), .1, requires_grad=True)
    p = m5a_loss(predicted, x, true, rs)
    assert p['residual'].item() == pytest.approx(.01)
    assert p['position'].item() == pytest.approx(.01)
    expected_v = ((.6 ** 2)*2) / (15*2)
    expected_acc = ((2.0 ** 2)*2) / (14*2)
    assert p['velocity'].item() == pytest.approx(expected_v)
    assert p['acceleration'].item() == pytest.approx(expected_acc)
    expected_penalty = ((6 * math.sqrt(2) - 3) / 3) ** 2 / 14
    assert p['penalty'].item() == pytest.approx(expected_penalty)
    assert p['total'].item() == pytest.approx(.01+.15*.01+.02*expected_v+.002*expected_acc+.001*expected_penalty)
    p['total'].backward(); assert torch.isfinite(predicted.grad).all()
    with pytest.raises(ValueError): m5a_loss(predicted, x[:,:,:3], true, rs)


def test_training_deterministic_update_and_validation_no_update():
    xs, rs = scalers()
    train = next(iter(DataLoader(VesselTrainingData(sample_split()), batch_size=4)))
    val = DataLoader(VesselTrainingData(sample_split('validation')),batch_size=4)
    outputs=[]
    for _ in range(2):
        torch.manual_seed(20261110); model=ResidualGRU(); opt=torch.optim.AdamW(model.parameters(),lr=.0025,weight_decay=.0001)
        initial=copy.deepcopy(model.state_dict()); loss=train_step(model,opt,train,xs,rs,'cpu')
        assert any(not torch.equal(initial[k],v) for k,v in model.state_dict().items())
        before=copy.deepcopy(model.state_dict()); metrics=validate(model,val,xs,rs,'cpu')
        assert all(torch.equal(before[k],v) for k,v in model.state_dict().items())
        assert metrics['vessels']==4 and math.isfinite(metrics['real_ais_ade_nm'])
        outputs.append((loss,model.state_dict()))
        train['split']=['validation']*4
        with pytest.raises(ValueError): train_step(model,opt,train,xs,rs,'cpu')
        train['split']=['train']*4
    assert outputs[0][0] == outputs[1][0]
    assert all(torch.equal(outputs[0][1][k],v) for k,v in outputs[1][1].items())


def test_metrics_and_checkpoint_gate():
    anchor=torch.zeros((1,2),dtype=torch.float64)
    points=torch.arange(1,16,dtype=torch.float64)[None,:,None]*torch.tensor([[[0.,1.]]],dtype=torch.float64)/60
    assert not severe_qc(points,anchor).any()
    assert checkpoint_improved(1.,.99,0)
    assert not checkpoint_improved(1.,.99,1)
    assert not checkpoint_improved(1.,1.-1e-8,0)
    with pytest.raises(ValueError): checkpoint_improved(1.,float('nan'),0)


def test_validation_ade_fde_known_values():
    xs, rs = scalers()
    split = sample_split('validation')
    split.X[:] = 0
    split.displacement[:, :, 0] = 1
    class ZeroModel(torch.nn.Module):
        def forward(self, x):
            return torch.zeros((len(x), 15, 2), dtype=x.dtype, device=x.device)
    result = validate(ZeroModel(), DataLoader(VesselTrainingData(split), batch_size=2), xs, rs, 'cpu')
    assert result['ade_nm'] == pytest.approx(1.)
    assert result['fde_nm'] == pytest.approx(1.)
    assert result['real_ais_ade_nm'] == pytest.approx(1.)


def test_cli_requires_explicit_mode():
    path=Path(__file__).resolve().parents[2]/'scripts/train_m5a.py'
    result=subprocess.run([sys.executable,str(path),'--dataset-root','unused','--output-dir','unused'],capture_output=True,text=True)
    assert result.returncode != 0 and '--smoke' in result.stderr
