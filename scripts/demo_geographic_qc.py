"""Geographic and frozen-risk comparison of full synthetic replay."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,math
import numpy as np,pandas as pd,geopandas as gpd,shapely
from shapely.geometry import Point,LineString,MultiLineString,box
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/s5_demo_geographic_fix';LAND=ROOT/'data/geography/ne_10m_land.zip';OSM=ROOT/'data/geography/osm_map_15_10_55_50_15_50_55_90.osm'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def to_xy(points,transformer):
 a=np.asarray(points,float);x,y=transformer.transform(a[:,1],a[:,0]);return np.column_stack((x,y))
def objects(points,transformer):
 xy=to_xy(points,transformer);return [Point(p) for p in xy],[LineString([a,b]) for a,b in zip(xy[:-1],xy[1:])]
def count_intersections(land,geom):
 return int(np.count_nonzero(shapely.intersects(land,np.asarray(geom,dtype=object)))) if geom else 0
def audit_geo(payload,land,transformer):
 events=payload['events'];raw=[];hist_segments=[];all_lines=[];all_geo=[]
 for vessel in sorted({e['vessel_id'] for e in events}):
  es=sorted((e for e in events if e['vessel_id']==vessel),key=lambda x:x['timestamp_utc']);seq=[[e['latitude'],e['longitude']] for e in es];pts,lines=objects(seq,transformer);raw+=pts;hist_segments+=lines;all_lines+=lines;all_geo+=seq
 groups={'m5a':{'points':[],'segments':[]},'cv':{'points':[],'segments':[]}};cpa=[];eligible=0;fallback=[];per_anchor={}
 for row in payload['rows']:
  minute=row['minute'];per_anchor.setdefault(str(minute),{'eligible':0,'unavailable':0})
  if 'm5a_geo' not in row:per_anchor[str(minute)]['unavailable']+=1;continue
  eligible+=1;per_anchor[str(minute)]['eligible']+=1
  if row['active_model']!='M5A' or row['fallback']:fallback.append({'minute':minute,'vessels':row['vessels'],'active_model':row['active_model']})
  assert len(row['m5a_geo'])==len(row['cv_geo'])==2
  lat0,lon0=row['origin'];ca=math.cos(math.radians(lat0))
  for j in range(2):
   e,n=row['anchors_en'][j];anchor=[lat0+n/60,lon0+e/(60*ca)]
   for kind in ('m5a','cv'):
    seq=row[kind+'_geo'][j];assert len(seq)==15;points,segments=objects([anchor]+seq,transformer);groups[kind]['points']+=points[1:];groups[kind]['segments']+=segments;all_lines+=segments;all_geo += seq
   cpa.append(Point(to_xy([row['m5a_geo'][j][row['predicted_closest_time_minutes']-1]],transformer)[0]))
 geo=np.asarray(all_geo);footprint=MultiLineString([list(line.coords) for line in all_lines]);osm_bbox=(15.10,55.50,15.50,55.90);inside_osm=bool((geo[:,1]>=osm_bbox[0]).all() and (geo[:,1]<=osm_bbox[2]).all() and (geo[:,0]>=osm_bbox[1]).all() and (geo[:,0]<=osm_bbox[3]).all())
 return {'raw_points':len(raw),'raw_points_on_land':count_intersections(land,raw),'history_segments':len(hist_segments),'history_segments_intersecting_land':count_intersections(land,hist_segments),'m5a_points':len(groups['m5a']['points']),'m5a_points_on_land':count_intersections(land,groups['m5a']['points']),'m5a_segments':len(groups['m5a']['segments']),'m5a_segments_intersecting_land':count_intersections(land,groups['m5a']['segments']),'cv_points':len(groups['cv']['points']),'cv_points_on_land':count_intersections(land,groups['cv']['points']),'cv_segments':len(groups['cv']['segments']),'cv_segments_intersecting_land':count_intersections(land,groups['cv']['segments']),'cpa_markers':len(cpa),'cpa_markers_on_land':count_intersections(land,cpa),'eligible_pair_anchors':eligible,'anchors':per_anchor,'fallbacks':fallback,'min_distance_to_mapped_land_km':float(land.distance(footprint)/1000),'geographic_bbox':{'lat_min':float(geo[:,0].min()),'lat_max':float(geo[:,0].max()),'lon_min':float(geo[:,1].min()),'lon_max':float(geo[:,1].max())},'all_points_inside_osm_bbox':inside_osm}
def compare(a,b):
 aa={(x['minute'],tuple(x['vessels'])):x for x in a['rows']};bb={(x['minute'],tuple(x['vessels'])):x for x in b['rows']};assert aa.keys()==bb.keys();fields=['risk_score','current_dcpa_nm','current_tcpa_minutes','predicted_min_distance_nm','predicted_closest_time_minutes','pair_distance_nm'];maxdiff={k:0. for k in fields+['history_en','anchors_en','m5a_en','cv_en']};decision_diffs=[];table=[]
 for key in aa:
  x,y=aa[key],bb[key]
  if (x['decision_status'],x['alert'],x['active_model'],x['fallback'])!=(y['decision_status'],y['alert'],y['active_model'],y['fallback']):decision_diffs.append(str(key))
  for f in fields:
   if x.get(f) is None or y.get(f) is None:
    if x.get(f)!=y.get(f):decision_diffs.append(str(key)+' missing '+f)
   else:maxdiff[f]=max(maxdiff[f],abs(x[f]-y[f]))
  for f in ['history_en','anchors_en','m5a_en','cv_en']:
   if f in x and f in y:maxdiff[f]=max(maxdiff[f],float(np.max(np.abs(np.asarray(x[f])-np.asarray(y[f])))))
  if key[0] in (9,15):
   z={'minute':key[0],'vessels':'/'.join(key[1]),'old_status':x['decision_status'],'new_status':y['decision_status'],'old_alert':x['alert'],'new_alert':y['alert']}
   for f in fields:z['old_'+f]=x.get(f);z['new_'+f]=y.get(f);z['delta_'+f]=None if x.get(f) is None or y.get(f) is None else y[f]-x[f]
   table.append(z)
 pd.DataFrame(table).to_csv(OUT/'risk_comparison_0009_0015.csv',index=False)
 summaries={}
 for minute in (9,15):
  values=[x for x in b['rows'] if x['minute']==minute];summaries[str(minute)]={'alert':sum(x['alert'] is True for x in values),'no_alert':sum(x['alert'] is False for x in values),'unavailable':sum(x['alert'] is None for x in values)}
 old,new=a['events'],b['events'];assert len(old)==len(new);oldorigin=(55.70,12.50);neworigin=(55.70,15.30);maxen=0.
 for x,y in zip(old,new):
  ea=(x['longitude']-oldorigin[1])*60*math.cos(math.radians(oldorigin[0]));eb=(y['longitude']-neworigin[1])*60*math.cos(math.radians(neworigin[0]));na=(x['latitude']-oldorigin[0])*60;nb=(y['latitude']-neworigin[0])*60;maxen=max(maxen,abs(ea-eb),abs(na-nb))
 return {'max_abs_differences':maxdiff,'max_event_en_difference_nm':maxen,'decision_differences':decision_diffs,'summaries':summaries}
def main():
 old=json.loads((OUT/'baseline.json').read_text(encoding='utf8'));new=json.loads((OUT/'relocated.json').read_text(encoding='utf8'))
 assert sha(LAND)=='e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc';g=gpd.read_file('zip://'+str(LAND),bbox=(10,53,18,59));g['geometry']=shapely.intersection(shapely.make_valid(g.geometry.array),box(10,53,18,59));land=g.loc[~g.geometry.is_empty].to_crs(32633).union_all();shapely.prepare(land);tf=Transformer.from_crs(4326,32633,always_xy=True)
 before=audit_geo(old,land,tf);after=audit_geo(new,land,tf);parity=compare(old,new);xml=ET.parse(OSM).getroot();coast=[e for e in xml if e.tag in ('node','way','relation') and any(t.get('k')=='natural' and t.get('v')=='coastline' for t in e.findall('tag'))];island=[e for e in xml if e.tag in ('node','way','relation') and any((t.get('k'),t.get('v')) in [('place','island'),('place','islet'),('natural','land')] for t in e.findall('tag'))]
 result={'natural_earth_land_sha256':sha(LAND),'natural_earth_scale':'1:10,000,000 (cartographic scale, not a meter accuracy)','natural_earth_version':'5.1.1','land_source':'https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/','distance_crs':'EPSG:32633 WGS84 / UTM 33N','osm_map_api':'https://api.openstreetmap.org/api/0.6/map?bbox=15.10,55.50,15.50,55.90','osm_sha256':sha(OSM),'osm_coastline_tagged_elements':len(coast),'osm_island_or_land_tagged_elements':len(island),'osm_bbox_query_limit':'OSM map API returns ways with a node in the bbox; it can miss a long crossing way with no node inside. OSM is supplementary and incomplete, not a nautical chart.','old':before,'new':after,'parity':parity}
 (OUT/'geographic_qc.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8');print(json.dumps(result,indent=2,allow_nan=False))
 if not all(after[k]==0 for k in ['raw_points_on_land','history_segments_intersecting_land','m5a_points_on_land','m5a_segments_intersecting_land','cv_points_on_land','cv_segments_intersecting_land','cpa_markers_on_land']) or after['fallbacks'] or parity['decision_differences'] or not after['all_points_inside_osm_bbox']:raise SystemExit('Geographic or decision QC failed')
if __name__=='__main__':main()
