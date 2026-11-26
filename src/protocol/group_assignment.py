"""Bounded deterministic group assignment; never uses predictions or scores."""
from collections import Counter
from hashlib import sha256
from .calibration_protocol import ProtocolError

FIELDS=('positive','negative','real_negative','synthetic_positive','close_positive','yang_lei')
MINIMUM=(30,30,30,30,10,30)


def _rank(seed, attempt, group):
    return sha256(f'{seed}:{attempt}:{group}'.encode('utf-8')).digest()


def partition_supported(heldout, total):
    """Both held-out and its complement must meet every P3 support."""
    return all(heldout.get(f,0)>=minimum and total.get(f,0)-heldout.get(f,0)>=minimum for f,minimum in zip(FIELDS,MINIMUM))


def assign_groups(groups, *, attempts=32, seed=20261124):
    """Input group records: id, encounters, and P3 counts; no outcome predictions.

    For each K 5,4,3,2, perform bounded seeded greedy searches, largest
    group first, then SHA256(seed, attempt, group id), assigning to fold
    minimizing sum of normalized squared load across all dimensions.
    Ties go to smaller fold index. All heldout and complementary calibration
    partitions must meet P3. Search failure is not a proof of infeasibility.
    """
    if not isinstance(groups,list) or not groups or type(attempts) is not int or attempts<1:
        raise ProtocolError('invalid groups or search budget')
    ids=set(); totals=Counter()
    for g in groups:
        ident=g.get('id'); n=g.get('encounters')
        if not isinstance(ident,str) or not ident.strip() or ident in ids or type(n) is not int or n<=0:
            raise ProtocolError('invalid/duplicate group id or count')
        ids.add(ident)
        if any(type(g.get(f)) is not int or not 0<=g[f]<=n for f in FIELDS):
            raise ProtocolError('invalid group support')
        if g['positive']+g['negative']!=n or g['close_positive']>g['synthetic_positive'] or g['synthetic_positive']>g['positive'] or g['real_negative']>g['negative']:
            raise ProtocolError('inconsistent group support')
        totals.update({f:g[f] for f in FIELDS});totals['encounters']+=n
    structural=[];searched=[]
    for k in (5,4,3,2):
        if len(groups)<k or any(totals[f]<k*minimum for f,minimum in zip(FIELDS,MINIMUM)):
            structural.append(k);continue
        searched.append(k)
        dims=('encounters',)+FIELDS
        for attempt in range(attempts):
            folds=[Counter() for _ in range(k)];assign={}
            ordered=sorted(groups,key=lambda g:(-g['encounters'],_rank(seed,attempt,g['id']),g['id']))
            for g in ordered:
                def objective(i):
                    return sum(((folds[i][f]+g[f])*k/max(totals[f],1))**2 for f in dims)
                idx=min(range(k),key=lambda i:(objective(i),i))
                assign[g['id']]=idx
                folds[idx].update({f:g[f] for f in dims})
            if all(partition_supported(fold,totals) for fold in folds):
                return {'status':'GROUPED_CV_READY','k':k,'assignment':assign,'attempts_per_k':attempts,'searched_k':searched,'structurally_impossible_k':structural,'search_is_exhaustive':False}
    status='GROUPED_CV_INFEASIBLE' if len(structural)==4 else 'GROUPED_CV_BLOCKED'
    return {'status':status,'k':None,'assignment':None,'attempts_per_k':attempts,'searched_k':searched,'structurally_impossible_k':structural,'search_is_exhaustive':False}
