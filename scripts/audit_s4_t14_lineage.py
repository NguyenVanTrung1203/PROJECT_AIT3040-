"""Metadata-only Validation lineage audit; never opens trajectory tensors or Test."""
import hashlib,json
from pathlib import Path
import pandas as pd
from src.protocol.calibration_primitives import validate_dependency_lineage

LOCK='21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441'
FILES=['manifests/dependency_groups.parquet','validation/manifests/validation_parent_mapping.csv',
       'validation/manifests/validation_source_windows.csv','validation/data/encounter_metadata.parquet',
       'validation/tensors/encounter_tensor_index.csv','validation/tensors/vessel_tensor_index.csv']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(root, upstream_synthetic_windows, upstream_synthetic_metadata):
    root=Path(root);manifest=root/'manifests/checksums_sha256.txt'
    lock=json.loads((root/'DATASET_LOCK_MANIFEST.json').read_text(encoding='utf-8'))
    if lock.get('dataset_version')!='final_dataset_1.0' or lock.get('lock_status')!='READY_AND_LOCKED' or lock.get('checksums_manifest_sha256')!=LOCK:raise ValueError('dataset lock version mismatch')
    if sha(manifest)!=LOCK:raise ValueError('dataset checksum manifest mismatch')
    expected={line.split(None,1)[1].strip().replace('\\','/'):line.split(None,1)[0] for line in manifest.read_text(encoding='utf-8').splitlines()}
    for name in FILES:
        if name not in expected or sha(root/name)!=expected[name]:raise ValueError('metadata checksum mismatch: '+name)
    g=pd.read_parquet(root/FILES[0],filters=[('package_split','==','validation')]); pm=pd.read_csv(root/FILES[1],dtype=str)
    w=pd.read_csv(root/FILES[2],dtype=str);meta=pd.read_parquet(root/FILES[3],columns=['encounter_id','original_encounter_id','data_source','parent_encounter_id','parent_source_group'])
    idx=pd.read_csv(root/FILES[4],dtype=str,usecols=['encounter_id']); vessels=pd.read_csv(root/FILES[5],dtype=str,usecols=['encounter_id','vessel_id']); upstream=pd.read_csv(upstream_synthetic_windows,dtype=str)
    if len(g)!=835 or g.encounter_id.duplicated().any() or g.dependency_group_id.isna().any() or set(g.encounter_id)!=set(idx.encounter_id):raise ValueError('encounter/group integrity failure')
    counts=g.dependency_group_id.value_counts()
    if len(counts)!=260 or counts.iloc[0]!=556:raise ValueError('group count mismatch')
    if len(pm)!=300 or pm.encounter_id.duplicated().any() or pm.parent_encounter_id.duplicated().any():raise ValueError('parent mapping ambiguity')
    synth=w[w.lineage_role=='synthetic_parent'].copy()
    j=synth.merge(pm,on='encounter_id',suffixes=('_w','_p'),validate='many_to_one')
    pairs=[('parent_encounter_id_w','parent_encounter_id_p'),('original_parent_id','parent_encounter_id_p'),('original_encounter_id_w','original_encounter_id_p'),('parent_source_group_y','parent_source_group')]
    if len(j)!=600 or not all(j[a].eq(j[b]).all() for a,b in pairs):raise ValueError('parent mapping mismatch')
    z=pm.merge(meta,on='encounter_id',suffixes=('_p','_m'),validate='one_to_one')
    if len(z)!=300 or not z.original_encounter_id_p.eq(z.original_encounter_id_m).all() or not z.parent_encounter_id_p.eq(z.parent_encounter_id_m).all() or not z.parent_source_group_p.eq(z.parent_source_group_m).all():raise ValueError('final metadata parent mismatch')
    keys=['original_parent_id','MMSI','source_track_id','source_start','source_end','grid_start','grid_end']
    upstream_meta=Path(upstream_synthetic_metadata)
    if sha(upstream_meta)!='bd1622643fc36a73a21b3cc986814bbcd44a13a71b5c2232f699538505e75b06':raise ValueError('upstream synthetic metadata hash mismatch')
    source_meta=pd.read_csv(upstream_meta,dtype=str)
    source_join=pm.merge(source_meta,left_on='original_encounter_id',right_on='synthetic_encounter_id',suffixes=('_p','_s'),validate='one_to_one')
    if len(source_join)!=300 or not source_join.parent_encounter_id_p.eq(source_join.parent_encounter_id_s).all() or not source_join.parent_source_group_p.eq(source_join.parent_source_group_s).all():raise ValueError('upstream synthetic identity mismatch')
    lineage=j.merge(source_meta,left_on='original_encounter_id_p',right_on='synthetic_encounter_id',validate='many_to_one',suffixes=('','_source'))
    same_a=lineage.MMSI.eq(lineage.MMSI_A) & lineage.source_track_id.eq(lineage.track_A)
    same_b=lineage.MMSI.eq(lineage.MMSI_B) & lineage.source_track_id.eq(lineage.track_B)
    if len(lineage)!=600 or not (same_a|same_b).all():raise ValueError('synthetic source MMSI/track mismatch')
    u=upstream.rename(columns={'encounter_id':'original_parent_id'})
    if u.duplicated(keys).any():raise ValueError('ambiguous upstream windows')
    joined=synth.merge(u,on=keys,how='left',validate='one_to_one',indicator=True)
    if len(joined)!=600 or not joined['_merge'].eq('both').all():raise ValueError('upstream source windows mismatch')
    if not w.MMSI.str.fullmatch(r'[0-9]{9}',na=False).all():raise ValueError('MMSI format invalid')
    real=meta[meta.data_source=='real_ais_kattegat_v3']; selected=pm[pm.parent_source_group=='selected_295']; other=pm[pm.parent_source_group=='unselected_candidates']
    if not real.original_encounter_id.is_unique or len(selected)!=150 or len(other)!=150 or not selected.parent_encounter_id.isin(real.original_encounter_id).all() or other.parent_encounter_id.isin(real.original_encounter_id).any():raise ValueError('parent source namespace mismatch')
    win_ids=w[['encounter_id','MMSI']].copy();win_ids['vessel_id']='physical_mmsi:'+win_ids.MMSI
    match=win_ids.merge(vessels,on=['encounter_id','vessel_id'],how='left',indicator=True)
    if len(match)!=len(w) or not match['_merge'].eq('both').all():raise ValueError('MMSI namespace/index mismatch')
    mapping=dict(zip(g.encounter_id,g.dependency_group_id))
    validate_dependency_lineage(mapping,list(zip(w.encounter_id,w.MMSI)),[])
    return {'status':'PARTIAL','encounters':len(g),'groups':len(counts),'largest':int(counts.iloc[0]),
            'parent_rows':len(j),'parent_rows_matched':len(joined),'parent_ids_unique':int(pm.parent_encounter_id.nunique()),
            'parent_final_id_matches':int(pm.parent_encounter_id.isin(g.encounter_id).sum()),
            'parent_source_groups':pm.parent_source_group.value_counts().to_dict(),
            'mmsi_track_rows_verified':int((same_a|same_b).sum()),'physical_namespace_index_rows_verified':len(match),'selected_parents_mapped_to_final_real':150,'unselected_parents_outside_final_real':150,
            'upstream_synthetic_metadata_sha256':sha(upstream_meta),'mmsi_format_valid':True,'connected_components_equal':True,'manifest_sha256':sha(root/FILES[0]),
            'upstream_synthetic_windows_sha256':sha(Path(upstream_synthetic_windows)),
            'limitation':'upstream window provenance/hash authority and real-world source identity need independent verification'}

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--dataset-root',required=True);a.add_argument('--synthetic-windows',required=True);a.add_argument('--synthetic-metadata',required=True);args=a.parse_args()
    print(json.dumps(audit(args.dataset_root,args.synthetic_windows,args.synthetic_metadata),indent=2))
