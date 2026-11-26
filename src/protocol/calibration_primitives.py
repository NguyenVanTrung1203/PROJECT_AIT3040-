"""Offline protocol primitives for synthetic fixtures; no dataset access or training."""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math


@dataclass(frozen=True)
class CountMetrics:
    tp: int
    fp: int
    fn: int
    tn: int

    def __post_init__(self):
        if any(type(x) is not int or x < 0 for x in (self.tp, self.fp, self.fn, self.tn)):
            raise ValueError('counts must be nonnegative integers')

    def ratio(self, metric):
        nums={'recall':(self.tp,self.tp+self.fn), 'fpr':(self.fp,self.fp+self.tn),
              'precision':(self.tp,self.tp+self.fp), 'f1':(2*self.tp,2*self.tp+self.fp+self.fn)}
        a,b=nums[metric]
        return Fraction(a,b) if b else None

    def support(self, metric):
        value=self.ratio(metric)
        if value is None:
            return 'NA', None
        positive=self.tp+self.fn; negative=self.fp+self.tn
        enough={'recall':positive>=30, 'fpr':negative>=30, 'precision':self.tp+self.fp>=20,
                'f1':positive>=30 and negative>=30}[metric]
        return ('VALID_SUPPORT' if enough else 'LOW_SUPPORT'),value


def subgroup_recall(tp, fn, minimum):
    if type(tp) is not int or type(fn) is not int or min(tp,fn)<0:
        raise ValueError('invalid counts')
    total=tp+fn
    if not total:return 'NA',None
    return ('VALID_SUPPORT' if total>=minimum else 'LOW_SUPPORT'), Fraction(tp,total)


def select_candidate(candidates):
    """D1 lexicographic selection from precomputed synthetic counts, no IO.

    candidates are dicts with k, overall CountMetrics, real CountMetrics,
    synthetic_tp_fn, close_tp_fn and severe_qc. Return k or None.
    """
    eligible=[]
    for c in candidates:
        k=c['k']; overall=c['overall']; real=c['real']
        if type(k) is not int or not 0<=k<=200:raise ValueError('invalid grid index')
        states=[overall.support('recall'),overall.support('f1'),real.support('fpr'),
                subgroup_recall(*c['synthetic_tp_fn'],30),subgroup_recall(*c['close_tp_fn'],10)]
        if any(status!='VALID_SUPPORT' for status,_ in states):continue
        recall,f1,fpr,syn,close=(v for _,v in states)
        if recall>=Fraction(9,10) and fpr<=Fraction(3,25) and syn>=Fraction(9,10) and close>=Fraction(19,20) and c['severe_qc']==0:
            eligible.append((f1,-fpr,recall,-k,k))
    return max(eligible)[-1] if eligible else None


def classify_prediction(score, grid_index):
    """Use verified score >= threshold comparator; no rounding or epsilon."""
    if not math.isfinite(score) or type(grid_index) is not int or not 0<=grid_index<=200:
        raise ValueError('invalid score or grid index')
    return score >= grid_index / 200


def confidence_support(valid_count, repetitions=5000):
    if type(valid_count) is not int or type(repetitions) is not int or not 0<=valid_count<=repetitions or repetitions!=5000:
        raise ValueError('invalid repetitions')
    return 'VALID_SUPPORT' if valid_count>=4750 else 'CI_INSUFFICIENT_VALID_REPETITIONS'


def check_dependency_rows(rows, expected_ids, *, manifest_bytes, expected_sha256, version):
    """Check generic manifest integrity; does not assert parent/source construction verified."""
    if not version or hashlib.sha256(manifest_bytes).hexdigest()!=expected_sha256:
        raise ValueError('DEPENDENCY_METADATA_INVALID')
    if len(rows)!=len(expected_ids) or len(set(expected_ids))!=len(expected_ids):
        raise ValueError('DEPENDENCY_METADATA_INVALID')
    got={}
    for encounter,group in rows:
        if not isinstance(encounter,str) or not encounter or encounter in got or not isinstance(group,str) or not group.strip():
            raise ValueError('DEPENDENCY_METADATA_INVALID')
        got[encounter]=group
    if set(got)!=set(expected_ids):raise ValueError('DEPENDENCY_METADATA_INVALID')
    return got


def paired_cluster_indices(group_ids, sampled_groups):
    """Return encounter positions once for each sampled group occurrence."""
    positions={}
    for i,g in enumerate(group_ids):
        if not isinstance(g,str) or not g.strip():raise ValueError('DEPENDENCY_METADATA_INVALID')
        positions.setdefault(g,[]).append(i)
    result=[]
    for g in sampled_groups:
        if g not in positions:raise ValueError('unknown dependency group')
        result.extend(positions[g])
    return tuple(result)


def ci_coverage(classifications):
    """Summarize exactly 5,000 replicate classifications without replacing samples."""
    allowed={'VALID_SUPPORT','LOW_SUPPORT','UNDEFINED','NO_FEASIBLE_THRESHOLD','EXECUTION_ERROR'}
    if len(classifications)!=5000 or any(c not in allowed for c in classifications):
        raise ValueError('invalid replicate classifications')
    if 'EXECUTION_ERROR' in classifications:
        return {'status':'EXECUTION_ERROR','valid':classifications.count('VALID_SUPPORT')}
    valid=classifications.count('VALID_SUPPORT')
    return {'status':confidence_support(valid),'valid':valid,'total':5000,
            'all_defined':classifications.count('VALID_SUPPORT')+classifications.count('LOW_SUPPORT'),
            'low_support':classifications.count('LOW_SUPPORT'),'undefined':classifications.count('UNDEFINED'),
            'no_feasible':classifications.count('NO_FEASIBLE_THRESHOLD')}


def comparison_gates(m5a, cv, *, m5a_real=None, cv_real=None):
    """D2 count gates only; Real AIS FPR requires its own matched counts."""
    if m5a_real is None or cv_real is None:
        return 'D2_BLOCKED'
    mr=[m5a.support('recall'),m5a_real.support('fpr'),m5a.support('f1')]
    cr=[cv.support('recall'),cv_real.support('fpr'),cv.support('f1')]
    if any(state!='VALID_SUPPORT' for state,_ in mr+cr):return 'D2_BLOCKED'
    recall,fpr,f1=(mr[i][1]-cr[i][1] for i in range(3))
    return 'COUNT_GATES_PASS' if recall>=Fraction(-1,100) and fpr<=Fraction(1,100) and f1>=Fraction(-1,100) else 'COUNT_GATES_FAIL'


def ade_gate(m5a, cv):
    """Compare float64 aggregates without D5 tolerance; zero baseline is NA."""
    import numpy as np
    m,c=np.float64(m5a),np.float64(cv)
    if not np.isfinite(m) or not np.isfinite(c) or c<=0 or m<0:return 'D2_BLOCKED'
    return 'D2_PASS' if m<=np.float64(1.10)*c else 'D2_FAIL'


def close_positive_comparison(close_ids, cv_detected, m5a_detected):
    ids=set(close_ids); cv=set(cv_detected); m5a=set(m5a_detected)
    if len(ids)!=len(close_ids) or not cv<=ids or not m5a<=ids:
        raise ValueError('invalid or duplicate close-positive identity')
    cv_fn=ids-cv; m_fn=ids-m5a
    return {'cv_fn':cv_fn,'m5a_fn':m_fn,'added_m5a_fn':m_fn-cv_fn,
            'm5a_only_detected':m5a-cv,'status':'D2_FAIL' if m_fn-cv_fn else 'D2_PASS'}


def paired_metric_delta(cv_value, m5a_value, cv_indices, m5a_indices):
    if tuple(cv_indices)!=tuple(m5a_indices):
        raise ValueError('paired sample mismatch')
    if cv_value is None or m5a_value is None:return None
    if not math.isfinite(cv_value) or not math.isfinite(m5a_value):
        raise ValueError('nonfinite metric')
    return m5a_value-cv_value


def threshold_stability_summary(results):
    """Count all attempted bootstrap samples; input values are k or None."""
    if len(results)!=5000:raise ValueError('expected 5000 attempts')
    if any(k is not None and (type(k) is not int or not 0<=k<=200) for k in results):
        raise ValueError('invalid threshold index')
    feasible=[k for k in results if k is not None]
    return {'feasible_count':len(feasible),'attempts':5000,
            'feasible_rate':len(feasible)/5000,'indices':feasible}


def summarize_bootstrap_metric(records):
    """Report per-metric all-defined and support-qualified percentile intervals.

    Consumes already-produced (classification, value) pairs; never resamples.
    An execution error raises rather than being misreported as NA.
    """
    import numpy as np
    if len(records)!=5000:raise ValueError('expected exactly 5000 recorded repetitions')
    classifications=[state for state,_ in records]
    summary=ci_coverage(classifications)
    if summary['status']=='EXECUTION_ERROR':raise RuntimeError('bootstrap execution error')
    defined=[];qualified=[]
    for state,value in records:
        if state in ('VALID_SUPPORT','LOW_SUPPORT'):
            if value is None or not math.isfinite(value):raise ValueError('defined metric must be finite')
            defined.append(float(value))
            if state=='VALID_SUPPORT':qualified.append(float(value))
        elif value is not None:
            raise ValueError('undefined or infeasible metric must not carry a value')
    summary['all_defined_ci']=np.percentile(defined,[2.5,97.5]).tolist() if defined else None
    summary['support_qualified_ci']=np.percentile(qualified,[2.5,97.5]).tolist() if len(qualified)>=4750 else None
    summary['qualified_interval_is_unbiased']=False
    return summary


def metric_support(metric, *, positive=0, negative=0, predicted_positive=0, subset=0, mathematical_defined=True):
    """P3 evaluation support, separate from mathematical definition."""
    counts=(positive,negative,predicted_positive,subset)
    if any(type(v) is not int or v<0 for v in counts):raise ValueError('invalid support count')
    if not mathematical_defined:return 'NA'
    predicates={'recall':positive>=30, 'overall_fpr':negative>=30,
                'real_fpr':negative>=30, 'synthetic_recall':positive>=30,
                'close_recall':subset>=10, 'precision':predicted_positive>=20,
                'f1':positive>=30 and negative>=30, 'roc_auc':positive>=30 and negative>=30,
                'average_precision':positive>=30 and negative>=30,
                'overall_ade':subset>=30, 'overall_fde':subset>=30,
                'source_ade':subset>=30, 'source_fde':subset>=30}
    if metric not in predicates:raise ValueError('unknown metric')
    if metric in ('recall','synthetic_recall') and positive==0:return 'NA'
    if metric in ('overall_fpr','real_fpr') and negative==0:return 'NA'
    if metric=='close_recall' and subset==0:return 'NA'
    if metric=='precision' and predicted_positive==0:return 'NA'
    if metric=='f1' and positive==0 and predicted_positive==0:return 'NA'
    if metric=='roc_auc' and (positive==0 or negative==0):return 'NA'
    if metric=='average_precision' and positive==0:return 'NA'
    if metric in ('overall_ade','overall_fde','source_ade','source_fde') and subset==0:return 'NA'
    return 'VALID_SUPPORT' if predicates[metric] else 'LOW_SUPPORT'


def validate_dependency_lineage(assignments, mmsi_links, parent_links):
    """Reconstruct dataset connected components from complete verified inputs.

    Caller must independently establish metadata version/hash/completeness and
    source identity. Missing links cannot be inferred and are never repaired.
    """
    ids=set(assignments)
    if not ids:raise ValueError('DEPENDENCY_METADATA_INVALID')
    parent={e:e for e in ids}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        if a not in ids or b not in ids:raise ValueError('DEPENDENCY_METADATA_INVALID')
        a,b=find(a),find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    by_mmsi={}
    for encounter,mmsi in mmsi_links:
        if encounter not in ids or not isinstance(mmsi,str) or len(mmsi)!=9 or not mmsi.isascii() or not mmsi.isdigit():
            raise ValueError('DEPENDENCY_METADATA_INVALID')
        if mmsi in by_mmsi:union(encounter,by_mmsi[mmsi])
        else:by_mmsi[mmsi]=encounter
    for child,source in parent_links:union(child,source)
    actual={e:'DEP_'+find(e) for e in ids}
    if actual!=assignments:raise ValueError('DEPENDENCY_METADATA_INVALID')
    return True


def validate_offline_dependency_baseline(rows, expected_ids, *, manifest_bytes, expected_sha256, version, mmsi_links, parent_links):
    """Enforce locked Validation counts and reconstructed complete lineage.

    The caller must verify source evidence is complete before supplying links;
    missing provenance is an error, never a singleton repair.
    """
    from collections import Counter
    if mmsi_links is None or parent_links is None:
        raise ValueError('DEPENDENCY_METADATA_INVALID')
    mapping=check_dependency_rows(rows,expected_ids,manifest_bytes=manifest_bytes,expected_sha256=expected_sha256,version=version)
    sizes=Counter(mapping.values())
    if len(mapping)!=835 or len(sizes)!=260 or max(sizes.values(),default=0)!=556:
        raise ValueError('DEPENDENCY_METADATA_INVALID')
    validate_dependency_lineage(mapping,mmsi_links,parent_links)
    return mapping


def classify_v1_evidence(evidence):
    """Classify audit evidence without loading artifacts or claiming replay success."""
    if not isinstance(evidence,dict):raise ValueError('invalid V1 evidence')
    required=('source_identity','architecture','checkpoint','scaler','dataset_provenance',
              'input_output','projection_qc','risk_compatibility','encounter_mapping',
              'artifact_integrity','replay_verified')
    if all(evidence.get(key) is True for key in required):return 'V1_BASELINE_REPRODUCIBLE'
    prediction_requirements=('predictions_available','prediction_hash_verified','prediction_split_verified',
                             'prediction_mapping_verified','prediction_semantics_verified')
    if all(evidence.get(key) is True for key in prediction_requirements):return 'V1_PREDICTIONS_ONLY'
    if any(evidence.get(key) is True for key in ('source_identity','checkpoint','predictions_available')):
        return 'V1_BASELINE_REVIEW_REQUIRED'
    if evidence.get('historical_metrics_available') is True:return 'V1_HISTORICAL_REFERENCE_ONLY'
    return 'V1_BASELINE_UNAVAILABLE'


def evaluate_d2(*, m5a_d1, cv_d1, m5a_counts, cv_counts, m5a_real, cv_real,
                overall_ade_m5a, overall_ade_cv, real_ade_m5a, real_ade_cv,
                overall_encounters, real_encounters, close_ids, cv_detected, m5a_detected, severe):
    """Combine all D2 gates without allowing count-only PASS to imply D2_PASS."""
    if cv_d1=='NO_FEASIBLE_THRESHOLD':return 'D2_CONDITIONAL'
    if cv_d1!='D1_PASS' or m5a_d1 not in ('D1_PASS','D1_FAIL'):return 'D2_BLOCKED'
    if m5a_d1=='D1_FAIL':return 'D2_FAIL'
    if type(overall_encounters) is not int or type(real_encounters) is not int or overall_encounters<30 or real_encounters<30 or len(close_ids)<10:
        return 'D2_BLOCKED'
    if type(severe) is not int or severe<0:return 'D2_BLOCKED'
    count=comparison_gates(m5a_counts,cv_counts,m5a_real=m5a_real,cv_real=cv_real)
    overall=ade_gate(overall_ade_m5a,overall_ade_cv);real=ade_gate(real_ade_m5a,real_ade_cv)
    close=close_positive_comparison(close_ids,cv_detected,m5a_detected)['status']
    if 'D2_BLOCKED' in (count,overall,real):return 'D2_BLOCKED'
    if count!='COUNT_GATES_PASS' or overall!='D2_PASS' or real!='D2_PASS' or close!='D2_PASS' or severe!=0:return 'D2_FAIL'
    return 'D2_PASS'


def sample_cluster_ids(groups, *, seed=20261124):
    """One reproducible paired cluster sample; shared indices are used for both models."""
    import numpy as np
    groups=tuple(groups)
    if not groups or len(set(groups))!=len(groups) or any(not isinstance(g,str) or not g.strip() for g in groups):
        raise ValueError('invalid dependency groups')
    rng=np.random.default_rng(seed)
    return tuple(groups[i] for i in rng.integers(0,len(groups),size=len(groups)))
