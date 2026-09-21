"""Fresh hython: reference_acceptance.py NEW_OUTPUT. Actual joint negative + old rack compatibility."""
import json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local import rack_inspection
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty hython')
first=upsert('reference-hom',recipe='pipe_rack_reference');node=hou.node(first['path'])
assert first['check']['passed'] and first['check']['part_count']==187
g=hou.Geometry();g.merge(node.geometry())
ids={v.point().number() for p in g.prims() if p.attribValue('name')=='pipe2_gasket' for v in p.vertices()}
for point in g.points():
    if point.number() in ids:
        x,y,z=point.position();point.setPosition((x+.01,y,z))
bad=rack_inspection.inspect(node,g);assert not bad['passed'] and any('interfaces mismatch' in str(v) for v in bad['issues'])
plan=preflight('reference-hom',{'support_pitch':.4,'joint_offset_2':.2});assert not plan['ready'] and 'overlaps a support' in str(plan['errors'])
old=upsert('rack-regression',recipe='pipe_rack_sample');assert old['check']['passed'] and old['check']['geometry_sha256']=='7d4ed8107afff2da5fd4b4652a732013155fcda9915b17265757f7d10e999f48'
r=dict(passed=True,check=first['check'],joint_negative=bad['issues'],preflight_conflict=plan,old_rack_geometry_sha256=old['check']['geometry_sha256'])
(out/'report.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps({'passed':True,'geometry_sha256':first['check']['geometry_sha256']}))
