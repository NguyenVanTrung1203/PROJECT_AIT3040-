from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import pytest
import torch
from src.inference.m5a_wrapper import EncounterBatch, InferenceError, M5aInference, verify_artifacts

ART = Path('artifacts/checkpoints/s3_t10_20261124_seed20261110_run01')

@pytest.fixture(scope='module')
def model():
    return M5aInference(ART, 'cpu')

@pytest.fixture
def batch():
    x = torch.zeros((1,2,10,4), dtype=torch.float32)
    x[0,0,:,0] = torch.linspace(-.1,0,10)
    x[0,1,:,0] = torch.linspace(-.2,0,10)
    x[0,:,:,2] = 2
    anchors = torch.tensor([[[.1,0.],[1.,0.]]],dtype=torch.float64)
    t = datetime(2026,1,1,tzinfo=timezone.utc)
    return EncounterBatch(x, anchors, (('vessel-a','vessel-b'),), (t,), (tuple(t-timedelta(minutes=i) for i in range(9,-1,-1)),), ('YANG_LEI',), True, True)

def test_real_artifacts_and_cpu_inference(model,batch):
    out = model._predict_test_only(batch,allow_fallback=False)
    assert out['forecast_common_en_nm'].shape == (1,2,15,2)
    assert out['forecast_common_en_nm'].dtype == torch.float64
    assert out['vessel_ids'] == batch.vessel_ids and out['qc_status'] == 'PASS'
    assert out['forecast_timestamps'][0][-1] == batch.anchor_times[0] + timedelta(minutes=15)
    assert out['active_model'] == 'M5a' and not out['fallback_used'] and out['alert_triggered'] is None
    assert torch.equal(out['forecast_common_en_nm'], model._predict_test_only(batch)['forecast_common_en_nm'])

def test_auto_and_invalid_device():
    m = M5aInference(ART, 'auto')
    assert m.device.type == ('cuda' if torch.cuda.is_available() else 'cpu')
    with pytest.raises(InferenceError, match='device'):
        M5aInference(ART,'bogus')

def test_manifest_and_scaler_corruption(tmp_path):
    shutil.copytree(ART,tmp_path/'a')
    p=tmp_path/'a'
    (p/'x_scaler.json').write_text('{}')
    with pytest.raises(InferenceError) as exc:
        verify_artifacts(p)
    assert exc.value.code == 'ARTIFACT_INTEGRITY_FAILURE'
    with pytest.raises(InferenceError):
        M5aInference(p,'cpu')

@pytest.mark.parametrize('mutation,code', [
    (lambda b:replace(b, history=b.history[:,:,:9]), 'INSUFFICIENT_DATA'),
    (lambda b:replace(b, history=b.history.double()), 'INVALID_INPUT'),
    (lambda b:replace(b, history=torch.full_like(b.history,float('nan'))), 'INSUFFICIENT_DATA'),
    (lambda b:replace(b, vessel_ids=(('x','x'),)), 'INVALID_INPUT'),
    (lambda b:replace(b, feature_order=('wrong',)), 'INVALID_INPUT'),
    (lambda b:replace(b, frame='other'), 'INVALID_INPUT'),
    (lambda b:replace(b, anchor_times=(b.anchor_times[0]+timedelta(minutes=1),)), 'INVALID_INPUT'),
    (lambda b:replace(b, anchors=torch.zeros_like(b.anchors)), 'INVALID_INPUT'),
])
def test_reject_invalid_without_fallback(model,batch,mutation,code):
    with pytest.raises(InferenceError) as exc:
        model._predict_test_only(mutation(batch))
    assert exc.value.code == code

def test_technical_failure_only_fallback(model,batch,monkeypatch):
    def broken(*args,**kwargs):
        raise RuntimeError('simulated technical failure')
    monkeypatch.setattr(model.model, 'forward',broken)
    result=model._predict_test_only(batch)
    assert result['fallback_used'] and result['active_model']=='CV' and result['qc_status']=='PASS'
    with pytest.raises(InferenceError) as exc:
        model._predict_test_only(batch,allow_fallback=False)
    assert exc.value.code=='MODEL_TECHNICAL_FAILURE'
    with pytest.raises(InferenceError) as exc:
        model._predict_test_only(replace(batch,history=batch.history[:,:,:9]))
    assert exc.value.code=='INSUFFICIENT_DATA'

@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA unavailable')
def test_cuda_semantic_and_numerical_fixture(batch,model):
    other = M5aInference(ART,'cuda')
    a=model._predict_test_only(batch,allow_fallback=False); b=other._predict_test_only(batch,allow_fallback=False)
    for key in ('vessel_ids','forecast_timestamps','data_status','qc_status','fallback_used','active_model'):
        assert a[key] == b[key]
    assert torch.max(torch.abs(a['forecast_common_en_nm']-b['forecast_common_en_nm'].cpu())) < 5e-5

def test_future_or_label_cannot_be_passed(model,batch):
    with pytest.raises(TypeError):
        model._predict_test_only(batch, future_target=torch.zeros(1))
    with pytest.raises(TypeError):
        model._predict_test_only(batch, label=1)

@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA unavailable')
@pytest.mark.parametrize('velocity,offset', [((0.001, 0.0),0.1), ((35.,-20.),0.1), ((49.99,0.),0.1), ((-2.,3.),1000.)])
def test_device_edge_inputs(model,batch,velocity,offset):
    x=batch.history.clone(); x[:,:,:,2]=velocity[0]; x[:,:,:,3]=velocity[1]
    anchors=batch.anchors.clone(); anchors[0,1,0]=offset
    b=replace(batch,history=x,anchors=anchors)
    a=model._predict_test_only(b,allow_fallback=False)
    c=M5aInference(ART,'cuda')._predict_test_only(b,allow_fallback=False)
    assert a['qc_status']==c['qc_status']=='PASS'
    assert torch.max(torch.abs(a['forecast_common_en_nm']-c['forecast_common_en_nm'].cpu())) < 5e-5

@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA unavailable')
def test_error_and_fallback_classification_matches_devices(batch, monkeypatch):
    models=[M5aInference(ART,d) for d in ('cpu','cuda')]
    for m in models:
        with pytest.raises(InferenceError) as exc:
            m.predict(replace(batch,provenance_verified=True, in_scope_verified=True))
        assert exc.value.code=='INVALID_INPUT'
        def fail(*args,**kwargs):
            raise RuntimeError('technical failure')
        monkeypatch.setattr(m.model,'forward',fail)
        with pytest.raises(InferenceError) as exc:
            m._predict_test_only(batch,allow_fallback=False)
        assert exc.value.code=='MODEL_TECHNICAL_FAILURE'
        result=m._predict_test_only(batch)
        assert result['active_model']=='CV' and result['fallback_used'] and result['qc_status']=='PASS'

def test_caller_set_both_booleans_cannot_enable_runtime(model,batch):
    with pytest.raises(InferenceError) as exc:
        model.predict(replace(batch,provenance_verified=True,in_scope_verified=True))
    assert exc.value.code == 'INVALID_INPUT'
    assert model._predict_test_only(batch)['data_status'] == 'TEST_ONLY_UNVERIFIED'


def test_t11_fallback_failure_never_masquerades_as_forecast(model,batch,monkeypatch):
    import src.inference.m5a_wrapper as wrapper
    def fail_model(*a,**k):raise RuntimeError('technical error')
    def fail_cv(*a,**k):raise ValueError('CV unusable')
    monkeypatch.setattr(model.model,'forward',fail_model)
    monkeypatch.setattr(wrapper,'project_forecast',fail_cv)
    with pytest.raises(InferenceError) as exc:model._predict_test_only(batch)
    assert exc.value.code=='FORECAST_UNAVAILABLE'
