"""Paired clustered bootstrap primitives; no dataset IO or automatic execution.

The caller owns provenance validation. This module never establishes trusted
input or model lock. Only synthetic fixtures are run during STEP_02.
"""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score
from .calibration_primitives import CountMetrics, metric_support, select_candidate, comparison_gates, ade_gate

METRICS=('roc_auc','average_precision','f1','recall','real_fpr','ade','fde','close_recall')


@dataclass(frozen=True)
class PairedData:
    ids: tuple
    groups: tuple
    labels: tuple
    source: tuple
    close: tuple
    cv_ids: tuple
    cv_score: tuple
    cv_ade: tuple
    cv_fde: tuple
    cv_severe: tuple
    m5a_ids: tuple
    m5a_score: tuple
    m5a_ade: tuple
    m5a_fde: tuple
    m5a_severe: tuple


def validate_data(data):
    if not isinstance(data,PairedData):raise ValueError('expected PairedData')
    n=len(data.ids)
    if not n or len(set(data.ids))!=n or any(not isinstance(v,str) or not v for v in data.ids):raise ValueError('encounter identities must be unique')
    if data.cv_ids!=data.ids or data.m5a_ids!=data.ids:raise ValueError('paired encounter identity/order mismatch')
    names=('groups','labels','source','close','cv_score','cv_ade','cv_fde','cv_severe','m5a_score','m5a_ade','m5a_fde','m5a_severe')
    if any(len(getattr(data,key))!=n for key in names):raise ValueError('paired field lengths mismatch')
    if any(not isinstance(g,str) or not g.strip() for g in data.groups):raise ValueError('missing group')
    if any(not isinstance(y,(int,np.integer)) or isinstance(y,(bool,np.bool_)) or y not in (0,1) for y in data.labels):raise ValueError('invalid labels')
    if any(s not in ('REAL_AIS','SYNTHETIC_AIS','YANG_LEI') for s in data.source):raise ValueError('invalid source')
    if any((s=='REAL_AIS' and data.labels[i]!=0) or (s=='SYNTHETIC_AIS' and data.labels[i]!=1) for i,s in enumerate(data.source)):raise ValueError('source/label contract mismatch')
    if any(not isinstance(c,(bool,np.bool_)) or (c and (data.source[i]!='SYNTHETIC_AIS' or data.labels[i]!=1)) for i,c in enumerate(data.close)):raise ValueError('invalid close-positive')
    for m in ('cv','m5a'):
        for kind in ('score','ade','fde'):
            a=np.asarray(getattr(data,f'{m}_{kind}'))
            if a.dtype!=np.float64:raise ValueError('scores and trajectory errors must be float64')
            if not np.isfinite(a).all() or (a<0).any() or (kind=='score' and (a>1).any()):raise ValueError('nonfinite or out-of-range input')
        if any(not isinstance(x,(bool,np.bool_)) for x in getattr(data,f'{m}_severe')):raise ValueError('invalid severe QC flags')
    return data


def resample_plan(groups, *, repetitions=5000, seed=20261124):
    """G replacement draws/attempt, stable UTF-8-sorted group IDs; no retries."""
    groups=tuple(groups)
    if not groups or any(not isinstance(g,str) or not g.strip() for g in groups):raise ValueError('invalid group IDs')
    if type(repetitions) is not int or repetitions<1:raise ValueError('invalid repetitions')
    ordered=tuple(sorted(set(groups),key=lambda g:g.encode('utf-8')))
    rng=np.random.default_rng(seed)
    return tuple(tuple(ordered[int(i)] for i in rng.integers(0,len(ordered),size=len(ordered))) for _ in range(repetitions))


def _indices(groups,draws):
    positions={}
    for i,g in enumerate(groups):positions.setdefault(g,[]).append(i)
    if len(draws)!=len(positions):raise ValueError('draw count must equal group count')
    out=[]
    for g in draws:
        if g not in positions:raise ValueError('unknown sampled group')
        out.extend(positions[g])
    return np.asarray(out,dtype=np.int64)


def _counts(y,pred):
    return CountMetrics(int(np.sum((y==1)&pred)),int(np.sum((y==0)&pred)),int(np.sum((y==1)&~pred)),int(np.sum((y==0)&~pred)))


def _metric_values(data,idx,model,k):
    y=np.asarray(data.labels)[idx];src=np.asarray(data.source)[idx];cl=np.asarray(data.close)[idx]
    scores=np.asarray(getattr(data,f'{model}_score'),dtype=np.float64)[idx]
    pred=scores >= k/200
    all_counts=_counts(y,pred);real=_counts(y[src=='REAL_AIS'],pred[src=='REAL_AIS'])
    def count_entry(cm,metric):
        state,val=cm.support(metric);return ('UNDEFINED' if state=='NA' else state, float(val) if val is not None else None)
    result={'f1':count_entry(all_counts,'f1'),'recall':count_entry(all_counts,'recall'),'real_fpr':count_entry(real,'fpr')}
    for name,mask in [('close_recall',cl)]:
        c=_counts(y[mask],pred[mask]); value=c.ratio('recall');support=metric_support('close_recall',subset=int(mask.sum()),mathematical_defined=value is not None)
        result[name]=('UNDEFINED' if support=='NA' else support,float(value) if value is not None else None)
    for kind in ('ade','fde'):
        vals=np.asarray(getattr(data,f'{model}_{kind}'),dtype=np.float64)[idx]
        status=metric_support('overall_'+kind,subset=len(idx))
        result[kind]=('UNDEFINED' if status=='NA' else status,float(vals.mean()) if len(vals) else None)
    pos=int(np.sum(y==1));neg=int(np.sum(y==0))
    for name in ('roc_auc','average_precision'):
        defined=pos>0 and (neg>0 or name=='average_precision')
        status=metric_support(name,positive=pos,negative=neg,mathematical_defined=defined)
        value=(roc_auc_score(y,scores) if name=='roc_auc' else average_precision_score(y,scores)) if defined else None
        result[name]=('UNDEFINED' if status=='NA' else status,float(value) if value is not None else None)
    return result


def _candidate(data,idx,model,k):
    y=np.asarray(data.labels)[idx];src=np.asarray(data.source)[idx];close=np.asarray(data.close)[idx]
    pred=np.asarray(getattr(data,f'{model}_score'),dtype=np.float64)[idx]>=k/200
    syn=src=='SYNTHETIC_AIS';real=src=='REAL_AIS'
    return {'k':k,'overall':_counts(y,pred),'real':_counts(y[real],pred[real]),
            'synthetic_tp_fn':(int(np.sum((y==1)&syn&pred)),int(np.sum((y==1)&syn&~pred))),
            'close_tp_fn':(int(np.sum(close&pred)),int(np.sum(close&~pred))),
            'severe_qc':int(np.asarray(getattr(data,f'{model}_severe'))[idx].sum())}


def _sample_support(data,idx):
    y=np.asarray(data.labels)[idx];source=np.asarray(data.source)[idx];close=np.asarray(data.close)[idx]
    checks=(int(np.sum(y==1)),int(np.sum(y==0)),int(np.sum(source=='REAL_AIS')),
            int(np.sum(source=='SYNTHETIC_AIS')),int(np.sum(close)))
    minima=(30,30,30,30,10)
    if any(v==0 for v in checks):return 'UNDEFINED'
    if any(v<minimum for v,minimum in zip(checks,minima)):return 'LOW_SUPPORT'
    return 'VALID_SUPPORT'


def _choose(data,idx,model):
    return select_candidate([_candidate(data,idx,model,k) for k in range(201)])


def _d2(data,idx,ck,mk):
    if ck is None:return 'D2_CONDITIONAL'
    if mk is None:return 'D2_BLOCKED'
    c=_candidate(data,idx,'cv',ck);m=_candidate(data,idx,'m5a',mk)
    counts=comparison_gates(m['overall'],c['overall'],m5a_real=m['real'],cv_real=c['real'])
    src=np.asarray(data.source)[idx];real=src=='REAL_AIS'
    if len(idx)<30 or int(real.sum())<30 or int(np.asarray(data.close)[idx].sum())<10:return 'D2_BLOCKED'
    full=ade_gate(np.asarray(data.m5a_ade)[idx].mean(),np.asarray(data.cv_ade)[idx].mean())
    real_ade=ade_gate(np.asarray(data.m5a_ade)[idx][real].mean(),np.asarray(data.cv_ade)[idx][real].mean())
    cvpred=np.asarray(data.cv_score)[idx]>=ck/200;mpred=np.asarray(data.m5a_score)[idx]>=mk/200
    close=np.asarray(data.close)[idx]
    added=bool(np.any(close&cvpred&~mpred))
    if counts=='D2_BLOCKED' or 'D2_BLOCKED' in (full,real_ade):return 'D2_BLOCKED'
    return 'D2_PASS' if counts=='COUNT_GATES_PASS' and full==real_ade=='D2_PASS' and not added and m['severe_qc']==0 else 'D2_FAIL'


def _aggregate(records,attempts):
    counts=Counter(s for s,_ in records);valid=counts['VALID_SUPPORT']
    defined=[v for s,v in records if s in ('VALID_SUPPORT','LOW_SUPPORT') and v is not None]
    qualified=[v for s,v in records if s=='VALID_SUPPORT' and v is not None]
    full=attempts==5000;qualified_ok=full and valid>=4750 and counts['EXECUTION_ERROR']==0
    status='EXECUTION_ERROR' if counts['EXECUTION_ERROR'] else ('VALID_SUPPORT' if qualified_ok else ('CI_INSUFFICIENT_VALID_REPETITIONS' if full else 'SYNTHETIC_POLICY_ONLY'))
    return {'status':status,
            'attempts':attempts,'defined_count':len(defined),'valid_support_count':valid,
            'low_support_count':counts['LOW_SUPPORT'],'undefined_count':counts['UNDEFINED'],
            'no_feasible_count':counts['NO_FEASIBLE_THRESHOLD'],'execution_error_count':counts['EXECUTION_ERROR'],
            'valid_support_ratio':valid/attempts,'all_defined_descriptive_ci':np.percentile(defined,[2.5,97.5]).tolist() if defined else None,
            'support_qualified_ci':np.percentile(qualified,[2.5,97.5]).tolist() if qualified_ok else None,
            'support_qualified_ci_unbiased':False}


def run_bootstrap(data, *, cv_threshold_index, m5a_threshold_index, repetitions=5000, seed=20261124, mode='fixed', plan=None, fixture_mode=False):
    """L1 fixed or L2 stability; input is paired precomputed data, no IO.

    Small repetition counts are for synthetic tests only. A supplied plan must
    have exactly repetitions rows and the identical per-attempt plan is used
    for both models. Exceptions per attempt remain EXECUTION_ERROR; no retry.
    """
    validate_data(data)
    if (repetitions!=5000 or seed!=20261124 or plan is not None) and fixture_mode is not True:
        raise ValueError('nonstandard repetitions, seed or explicit plan require synthetic fixture mode')
    if mode not in ('fixed','stability'):raise ValueError('invalid mode')
    if any(type(k) is not int or not 0<=k<=200 for k in (cv_threshold_index,m5a_threshold_index)):raise ValueError('invalid fixed threshold index')
    if plan is None:plan=resample_plan(data.groups,repetitions=repetitions,seed=seed)
    if len(plan)!=repetitions:raise ValueError('plan length mismatch')
    records={m:[] for m in METRICS};details=[]
    for draws in plan:
        try:
            idx=_indices(data.groups,draws)
            ck=_choose(data,idx,'cv') if mode=='stability' else cv_threshold_index
            mk=_choose(data,idx,'m5a') if mode=='stability' else m5a_threshold_index
            cv=_metric_values(data,idx,'cv',ck) if ck is not None else None
            m=_metric_values(data,idx,'m5a',mk) if mk is not None else None
            support=_sample_support(data,idx)
            d2=_d2(data,idx,ck,mk) if mode=='stability' else None
            per_attempt={}
            for metric in METRICS:
                if cv is None or m is None:
                    per_attempt[metric]=('NO_FEASIBLE_THRESHOLD',None)
                    continue
                cs,cvv=cv[metric];ms,mv=m[metric]
                if cvv is None or mv is None:per_attempt[metric]=('UNDEFINED',None)
                else:per_attempt[metric]=('VALID_SUPPORT' if cs==ms=='VALID_SUPPORT' else 'LOW_SUPPORT',mv-cvv)
            for metric in METRICS:records[metric].append(per_attempt[metric])
            details.append({'draws':tuple(draws),'sample_indices':tuple(map(int,idx)), 'cv_threshold_index':ck,'m5a_threshold_index':mk,'cv_calibration_status':'FEASIBLE' if ck is not None else 'NO_FEASIBLE_THRESHOLD','m5a_calibration_status':'FEASIBLE' if mk is not None else 'NO_FEASIBLE_THRESHOLD','sample_support':support,'cv_metrics':cv,'m5a_metrics':m,'d2':d2,'status':'OK'})
        except Exception as exc:
            for metric in METRICS:records[metric].append(('EXECUTION_ERROR',None))
            details.append({'draws':tuple(draws),'status':'EXECUTION_ERROR','error_type':type(exc).__name__,'error':str(exc)})
    cv_ok=sum(d.get('cv_threshold_index') is not None for d in details);m_ok=sum(d.get('m5a_threshold_index') is not None for d in details)
    both=sum(d.get('cv_threshold_index') is not None and d.get('m5a_threshold_index') is not None for d in details)
    d2_counts=Counter(d.get('d2') for d in details if d.get('d2') is not None)
    return {'mode':mode,'attempts':len(details),'seed':seed,'details':details,'metrics':{m:_aggregate(r,repetitions) for m,r in records.items()},
            'stability':{'attempts':len(details),'cv_feasible':cv_ok,'cv_feasible_rate':cv_ok/repetitions,'m5a_feasible':m_ok,'m5a_feasible_rate':m_ok/repetitions,'both_feasible':both,'d2_comparable':d2_counts['D2_PASS']+d2_counts['D2_FAIL'],'d2_counts':{k:d2_counts[k] for k in ('D2_PASS','D2_FAIL','D2_CONDITIONAL','D2_BLOCKED')},
                         'sample_support_counts':dict(Counter(d.get('sample_support','EXECUTION_ERROR') for d in details)),
                         'cv_thresholds':[d['cv_threshold_index'] for d in details if d.get('cv_threshold_index') is not None],
                         'm5a_thresholds':[d['m5a_threshold_index'] for d in details if d.get('m5a_threshold_index') is not None]},
            'protocol_repetitions':5000,'official_ci_eligible':repetitions==5000 and not fixture_mode}
