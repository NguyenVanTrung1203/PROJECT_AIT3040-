from dataclasses import replace
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import pytest

from src.inference.m5a_wrapper import InferenceError, M5aInference
from src.inference.offline_validation import COLUMNS, load_validation, validate_history
from src.data.dataset_loader import DatasetLoader

ART = Path('artifacts/checkpoints/s3_t10_20261124_seed20261110_run01')

@pytest.fixture(scope='module')
def data():
    loader=DatasetLoader()
    split,_,_=load_validation(loader.root)
    history=pd.read_parquet(loader.root/'validation/data/validation_835.parquet',columns=COLUMNS,filters=[('is_history','==',True)])
    return loader,split,history

@pytest.fixture(scope='module')
def model():
    return M5aInference(ART,'cpu')


def test_caller_booleans_and_fake_verified_object_cannot_enter(model):
    class Verified:
        provenance_verified=True
        in_scope_verified=True
    for obj in (Verified(), {'provenance_verified':True}, {'in_scope_verified':True}):
        with pytest.raises(InferenceError) as exc:
            model.predict(obj)
        assert exc.value.code == 'INVALID_INPUT'
    with pytest.raises(InferenceError):
        model.predict_validation(Verified())


def test_bad_manifest_rejected_before_inference(data,model,tmp_path,monkeypatch):
    loader,_,_=data
    shutil.copy(loader.root/'DATASET_LOCK_MANIFEST.json',tmp_path/'DATASET_LOCK_MANIFEST.json')
    (tmp_path/'manifests').mkdir()
    (tmp_path/'manifests/checksums_sha256.txt').write_text('wrong checksum')
    def forbidden(*args,**kwargs):
        pytest.fail('inference executed on unverified dataset')
    monkeypatch.setattr(model.model,'forward',forbidden)
    with pytest.raises(InferenceError):
        model.predict_validation(tmp_path)


@pytest.mark.parametrize('kind', ['source', 'encounter', 'vessel', 'timestamp', 'future', 'missing_source', 'source_future', 'source_stale', 'missing_field', 'frame'])
def test_invalid_history_rejected(data,kind):
    _,s,original=data
    h=original.copy(deep=True)
    ix=h.index[0]
    if kind == 'source': h.loc[ix,'data_source']='unknown'
    elif kind == 'encounter': h.loc[ix,'encounter_id']='unrecognized'
    elif kind == 'vessel': h.loc[ix,'vessel_id']='unrecognized'
    elif kind == 'timestamp': h.loc[ix,'timestamp_utc']+=pd.Timedelta(seconds=1)
    elif kind == 'future': h.loc[ix,'timestamp_utc']=h.loc[ix,'anchor_timestamp']+pd.Timedelta(minutes=1)
    elif kind == 'missing_source': h.loc[ix,'original_source_timestamp_utc']=pd.NaT
    elif kind == 'source_future': h.loc[ix,'original_source_timestamp_utc']=h.loc[ix,'timestamp_utc']+pd.Timedelta(seconds=1)
    elif kind == 'source_stale': h.loc[ix,'original_source_timestamp_utc']=h.loc[ix,'timestamp_utc']-pd.Timedelta(seconds=61)
    elif kind == 'missing_field': h=h.drop(columns=['anchor_timestamp'])
    elif kind == 'frame': h.loc[ix,'LAT']+=0.01
    with pytest.raises(InferenceError): validate_history(s,h)


def test_wrong_ab_mapping_rejected(data):
    _,s,h=data
    pairs=s.pairs.copy(); pairs[0]=pairs[0,::-1]
    with pytest.raises(InferenceError): validate_history(replace(s,pairs=pairs),h)


def test_future_labels_and_targets_do_not_enter_tensor(data):
    _,s,h=data
    first=validate_history(s,h)
    # The checked history path and features must not depend on label or targets.
    changed=replace(s,labels=np.zeros_like(s.labels),common=np.zeros_like(s.common),displacement=np.zeros_like(s.displacement))
    second=validate_history(changed,h)
    assert first.equals(second)


def test_invalid_inputs_never_reach_model(data,model,monkeypatch):
    def forbidden(*args,**kwargs): pytest.fail('model ran for invalid input')
    monkeypatch.setattr(model.model,'forward',forbidden)
    with pytest.raises(InferenceError): model.predict({'provenance_verified':True, 'in_scope_verified':True})
    with pytest.raises(InferenceError): model.predict_validation(Path('nonexistent_dataset'))


def test_offline_verified_input_and_technical_fallback(data,model,monkeypatch):
    loader,_,_=data
    def fail(*args,**kwargs): raise RuntimeError('model execution failed')
    monkeypatch.setattr(model.model,'forward',fail)
    outputs,checksum=model.predict_validation(loader.root,batch_size=835)
    assert checksum['files_verified']==93
    assert sum(len(x['encounter_ids']) for x in outputs)==835
    assert outputs[0]['fallback_used'] and outputs[0]['active_model']=='CV'
    assert outputs[0]['input_scope']=='LOCKED_OFFLINE_VALIDATION'
