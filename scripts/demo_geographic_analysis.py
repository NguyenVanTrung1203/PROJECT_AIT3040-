"""Offline synthetic replay audit: frozen runtime, no training or calibration."""
from pathlib import Path
import sys,os,json,math
import numpy as np
repo=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]).resolve();envfile=Path(sys.argv[3])
for line in envfile.read_text(encoding='utf8').splitlines():
 s=line.strip()
 if not s or s.startswith('#') or '=' not in s:continue
 k,v=s.split('=',1);os.environ[k.strip()]=v.strip().strip('"').strip("'")
os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.path.insert(0,str(repo))
import torch
from src.runtime.trusted_fixture import FixtureProvider,_events
from src.runtime.config import load_config
from src.runtime.m5a_service import M5aRuntime
from src.runtime.risk_service import FixtureRiskHarness
from src.models.kinematics import cv_displacement,project_forecast
torch.set_num_threads(1);provider=FixtureProvider(5);provider.create('2024-11-01T00:09:00Z');model=M5aRuntime(load_config(os.environ),provider);harness=FixtureRiskHarness(provider,model);rows=[]
try:
 for minute in range(9,21):
  if minute!=9:provider.control('SEEK',f'2024-11-01T00:{minute:02d}:00Z')
  snap=provider.snapshot();coverage=provider.candidates(snap)
  for j,c in enumerate(coverage.candidates):
   risk=harness.evaluate(snap,c,f'geo-{minute}-{j}');row={'minute':minute,'vessels':list(c.vessels),'reason':c.unavailable_reason,'decision_status':risk['decision_status'],'alert':risk['alert_triggered'],'risk_score':risk['risk_score'],'current_dcpa_nm':risk['current_dcpa_nm'],'current_tcpa_minutes':risk['current_tcpa_minutes'],'predicted_min_distance_nm':risk['predicted_min_distance_nm'],'predicted_closest_time_minutes':risk['predicted_closest_time_minutes'],'active_model':risk['model_status']['active_model'],'fallback':risk['model_status']['fallback_used']}
   if risk['forecast']:
    encounter,_=provider.encounter(snap,c);feat=provider.features(snap,encounter);x=torch.from_numpy(feat.history.copy());a=torch.from_numpy(feat.anchors_en.copy());v=x[:,-1,2:].to(a.dtype)
    with torch.inference_mode(): cv=project_forecast(a[:,None,:]+cv_displacement(v),a,v).cpu().numpy()
    lat0,lon0=feat.origin_lat_lon;cos0=math.cos(math.radians(lat0));cvgeo=np.stack((cv[:,:,1]/60+lat0,cv[:,:,0]/(60*cos0)+lon0),axis=-1)
    row.update({'history_en':feat.history.tolist(),'anchors_en':feat.anchors_en.tolist(),'m5a_en':risk['forecast']['forecast_common_en_nm'],'m5a_geo':risk['forecast']['forecast_lat_lon'],'cv_en':cv.tolist(),'cv_geo':cvgeo.tolist(),'origin':list(feat.origin_lat_lon),'pair_distance_nm':float(np.linalg.norm(feat.anchors_en[1]-feat.anchors_en[0]))})
   rows.append(row)
  print('anchor',minute,'eligible',coverage.eligible,'unavailable',coverage.unavailable,flush=True)
finally:model.close()
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'repo':str(repo),'events':_events(),'rows':rows},indent=2,allow_nan=False),encoding='utf8');print('wrote',out,flush=True)
