import hashlib
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import torch
from scripts import run_s4_t14_step03_batch01 as batch


def make_forecasts():
    t=pd.Timestamp('2026-01-01T00:00:00Z')
    s=SimpleNamespace(pairs=np.array([[0,1],[2,3]]),encounters=pd.DataFrame({'encounter_id':['e1','e2']}),metadata=pd.DataFrame({'anchor_timestamp':[t,t]}),vessels=pd.DataFrame({'vessel_id':['a','b','c','d']}))
    out={'fallback_used':False,'qc_status':'PASS','input_scope':'LOCKED_OFFLINE_VALIDATION','forecast_common_en_nm':torch.zeros((2,2,15,2),dtype=torch.float64),'x_rows':s.pairs.copy(),'encounter_ids':('e1','e2'),'vessel_ids':(('a','b'),('c','d')),'forecast_timestamps':tuple(tuple((t+pd.Timedelta(minutes=k)).to_pydatetime() for k in range(1,16)) for _ in range(2))}
    return s,out


def test_pairing_accepts_permuted_encounters():
    s,o=make_forecasts();o['encounter_ids']=('e2','e1');o['x_rows']=o['x_rows'][::-1].copy();o['vessel_ids']=o['vessel_ids'][::-1]
    assert batch.verify_pairing(s,[o]).shape==(2,2,15,2)

@pytest.mark.parametrize('mutation',[lambda o:o.update(encounter_ids=('e1','e1')),lambda o:o.update(encounter_ids=('e1','missing')),lambda o:o.update(vessel_ids=(('b','a'),('c','d'))),lambda o:o.update(fallback_used=True),lambda o:o.update(qc_status='SEVERE'),lambda o:o.update(forecast_common_en_nm=torch.full((2,2,15,2),float('nan'),dtype=torch.float64)),lambda o:o.update(forecast_timestamps=((),()))])
def test_pairing_rejects_invalid_output(mutation):
    s,o=make_forecasts();mutation(o)
    with pytest.raises(ValueError):batch.verify_pairing(s,[o])


def test_exact_comparison_detects_single_bit_difference():
    a={'score':np.array([1.,2.])};b={'score':np.array([1.,np.nextafter(2.,3.)])}
    summary,bad=batch.compare_arrays(a,b,['a','b'])
    assert bad==['score'] and summary['score']['affected_encounter_ids']==['b'] and summary['score']['mismatches']==1


def test_exact_comparison_categorical_and_nonfinite():
    assert batch.compare_arrays({'role':np.array(['A'])},{'role':np.array(['B'])},['a'])[1]==['role']
    with pytest.raises(ValueError):batch.compare_arrays({'x':np.array([np.nan])},{'x':np.array([np.nan])},['a'])


def test_output_checksum_rejects_mutation(tmp_path):
    p=tmp_path/'artifact';p.write_bytes(b'initial');(tmp_path/'checksums.sha256').write_text(hashlib.sha256(b'initial').hexdigest()+'  artifact\n')
    assert batch.verify_output(tmp_path)==1
    p.write_bytes(b'altered')
    with pytest.raises(ValueError):batch.verify_output(tmp_path)


def test_reuse_rejects_failed_status(tmp_path):
    (tmp_path/'run_status.json').write_text(json.dumps({'status':'FAILED'}));(tmp_path/'run_manifest.json').write_text('{}')
    paths=['run_status.json','run_manifest.json'];(tmp_path/'checksums.sha256').write_text(''.join(batch.digest(tmp_path/p)+'  '+p+'\n' for p in paths))
    with pytest.raises(ValueError,match='approved Validation'):batch.verify_reuse(tmp_path,tmp_path,tmp_path,tmp_path)


def test_protocol_state_is_pinned():
    from src.protocol.calibration_protocol import validate_protocol,load_protocol,ProtocolError
    protocol=load_protocol(batch.ROOT/'configs/s4_calibration_protocol.yaml');protocol['model_lock']['locked']=True
    with pytest.raises(ProtocolError):validate_protocol(protocol)


def test_model_and_dataset_hash_mismatch_rejected(tmp_path):
    from src.inference.m5a_wrapper import verify_artifacts,InferenceError
    with pytest.raises(InferenceError):verify_artifacts(tmp_path)
    (tmp_path/'DATASET_LOCK_MANIFEST.json').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='dataset lock hash mismatch'):batch.verify_dataset_lock(tmp_path)


def test_test_scope_is_rejected_before_inference(monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['runner','--scope','test','--dataset-root','x','--artifact-dir','x','--original-v4','x','--output-root','x'])
    with pytest.raises(SystemExit):batch.main()


def test_q1_guard_rejects_test_deserialization(monkeypatch,tmp_path):
    import scripts.q1_test_access_guard as guard
    monkeypatch.setattr(guard,'root',tmp_path/'test')
    monkeypatch.setitem(guard.counters,'blocked_deserialization',0)
    called=[]
    protected=guard.checked(lambda p:called.append(p))
    with pytest.raises(RuntimeError,match='prohibits Test'):protected(tmp_path/'test'/'labels.npy')
    assert not called


def test_original_and_packaged_receive_identical_independent_inputs():
    calls=[]
    class Engine:
        def __init__(self,change=False): self.change=change
        def calculate(self,features,forecast):
            calls.append((features['last'].copy(),forecast.copy()))
            value=features['last'][:,0].copy()
            if self.change: value[0]=np.nextafter(value[0],np.inf)
            features['last'][:]=999
            forecast[:]=999
            return {'CC-DRI':value},{'detail':value.copy()}
    feat={'last':np.array([[1.,2.]])};forecast=np.zeros((1,2,15,2))
    _,_,summary,bad=batch.score_pair(Engine(),Engine(),feat,forecast,['e'])
    assert not bad and all(x['mismatches']==0 for x in summary.values())
    assert np.array_equal(calls[0][0],calls[1][0]) and np.array_equal(calls[0][1],calls[1][1])
    assert feat['last'][0,0]==1 and np.all(forecast==0)
    assert batch.score_pair(Engine(),Engine(True),feat,forecast,['e'])[3]
