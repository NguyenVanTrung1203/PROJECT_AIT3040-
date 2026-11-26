"""History-only CPA and rule scoring; mirrors feasibility pilot.py formulas."""
from pathlib import Path
import json,numpy as np,pandas as pd,joblib,torch
from torch import nn
F=Path(__file__).resolve().parents[1];D=F.parent/'DATASET_FINAL'
class GRU(nn.Module):
 def __init__(self):super().__init__();self.gru=nn.GRU(4,48,batch_first=True);self.head=nn.Sequential(nn.Linear(48,96),nn.ReLU(),nn.Linear(96,30))
 def forward(self,x):_,h=self.gru(x);return self.head(h[-1]).reshape(-1,15,2)
def angle(a,b):return (np.asarray(a)-b+180)%360-180
def cpa(pa,va,pb,vb,horizon=15):
 r=np.asarray(pb)-pa;v=np.asarray(vb)-va;den=(v*v).sum(-1);raw=np.divide(-(r*v).sum(-1),den,out=np.zeros_like(den,dtype=float),where=den>1e-9)*60;t=np.clip(raw,0,horizon);return np.linalg.norm(r+v*t[...,None]/60,axis=-1),t,raw
def score(d,t,scale=.14):return 1/(1+np.exp(np.clip((np.asarray(d)-.65)/scale,-100,100)))*(1-.25*np.minimum(t,15)/15)
def infer_roles(pos,vel):
 p=pos[:,:,:3].mean(2);v=vel[:,:,:3].mean(2);cog=np.rad2deg(np.arctan2(v[:,:,0],v[:,:,1]))%360;r=p[:,1]-p[:,0];bearing=np.rad2deg(np.arctan2(r[:,0],r[:,1]))%360;ba=(bearing-cog[:,0])%360;bb=(bearing+180-cog[:,1])%360;delta=np.abs(angle(cog[:,0],cog[:,1]));speed=np.linalg.norm(v,axis=-1);roles=np.full(len(p),'unknown',dtype='U12');scene=np.full(len(p),'unknown',dtype='U24')
 for i in range(len(p)):
  if abs(delta[i]-180)<=25 and abs(angle(ba[i],0))<=20 and abs(angle(bb[i],0))<=20:roles[i]='both';scene[i]='head_on'
  elif delta[i]<=30 and 112.5<ba[i]<247.5 and speed[i,1]>speed[i,0]:roles[i]='B';scene[i]='overtaking'
  elif delta[i]<=30 and 112.5<bb[i]<247.5 and speed[i,0]>speed[i,1]:roles[i]='A';scene[i]='overtaking'
  elif 30<=delta[i]<=150 and 15<=ba[i]<=165:roles[i]='A';scene[i]='crossing_starboard'
  elif 30<=delta[i]<=150 and 195<=ba[i]<=345:roles[i]='B';scene[i]='crossing_port'
 return roles,scene
def rule_component(cog,sog,roles):
 dc=angle(cog[:,:,-1],cog[:,:,0]);ds=sog[:,:,-1]-sog[:,:,0];violation=~((dc>=10)|((dc>=5)&(ds<=-.6))) | (dc<=-4);out=np.full(len(roles),.5)
 for role,idx in [('A',0),('B',1)]:out[roles==role]=violation[roles==role,idx]
 out[roles=='both']=violation[roles=='both'].mean(1)
 return out
def history_features(split):
 n={'validation':835,'test':1320}[split];root=D/split;X=np.load(root/'tensors/X_unscaled.npy').reshape(n,2,10,4);anchor=np.load(root/'tensors/anchor_positions_EN_nm.npy');idx=pd.read_csv(root/'tensors/encounter_tensor_index.csv');d=pd.read_parquet(root/f'data/{split}_{n}.parquet');d=d[d.is_history].copy();rank={e:i for i,e in enumerate(idx.encounter_id)};d['_i']=d.encounter_id.map(rank);d=d.sort_values(['_i','vessel','relative_minute']);a=d[['SOG','COG']].to_numpy().reshape(n,2,10,2);pos=X[:,:,:,:2].astype(float)+anchor[:,:,None];vel=X[:,:,:,2:].astype(float);roles,scene=infer_roles(pos,vel);rule=rule_component(a[:,:,:,1],a[:,:,:,0],roles);return {'X':X.reshape(-1,10,4),'last':anchor,'pos':pos,'vel':vel,'roles':roles,'inferred_scenario':scene,'rule':rule},idx
def predict_model(model,x,xs,ys,batch_size=1024):
 xn=xs.transform(x.reshape(-1,4)).reshape(x.shape).astype('float32');out=[];model.eval()
 with torch.no_grad():
  for i in range(0,len(xn),batch_size):out.append(model(torch.from_numpy(xn[i:i+batch_size])).cpu().numpy())
 q=np.concatenate(out);return q*ys.scale_+ys.mean_
def calculate(feat,pred):
 p=feat['last'];v=feat['vel'][:,:,-1];d,t,raw=cpa(p[:,0],v[:,0],p[:,1],v[:,1]);current=score(d,t,.16);cv=p[:,:,None]+v[:,:,None]*np.arange(1,16)[None,None,:,None]/60
 def predicted(q):
  dist=np.linalg.norm(q[:,0]-q[:,1],axis=-1);i=dist.argmin(1);return score(dist[np.arange(len(dist)),i],i+1),dist.min(1),i+1
 cs,cd,ct=predicted(cv);gs,gd,gt=predicted(pred);rule=feat['rule'];scores={'Current-CPA':current,'CV-P-CPA':cs,'GRU-P-CPA':gs,'CC-DRI':.68*gs+.12*current+.20*rule};assert all(np.isfinite(a).all() for a in scores.values());return scores,{'dcpa_nm':d,'tcpa_clipped_min':t,'tcpa_raw_min':raw,'cv_common':cv,'cv_dmin_nm':cd,'cv_tmin':ct,'pred_dmin_nm':gd,'pred_tmin':gt,'rule':rule}
