"""Fresh hython: u_bolt_acceptance.py OUTPUT [LEGACY_STRAIGHT_HIP LEGACY_ELBOW_HIP]."""
import json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local.sample_inspection import inspect,inspect_geometry

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh headless process')
created=upsert('u-bolt-check');node=hou.node(created['path']);report={'passed':False,'measurements':created['check']['measurements']}
assert created['check']['passed'] and created['check']['part_count']==77
geometry=hou.Geometry();geometry.merge(node.geometry())
ids={v.point().number() for prim in geometry.prims() if prim.attribValue('name')=='support_pos_0_clamp' for v in prim.vertices()}
h=created['parameters']['diameter']/2+.044
for point in geometry.points():
    if point.number() in ids:
        x,y,z=point.position();point.setPosition((x,2*h-y,z))
wrong=inspect_geometry(node,geometry,created['parameters'])
assert not wrong['passed'] and any('open U' in str(v) for v in wrong['issues'])
report['upside_down_negative']=wrong['issues'];report['legacy']=[]
for hip in sys.argv[2:]:
    hou.hipFile.load(str(Path(hip).resolve()),suppress_save_prompt=True)
    nodes=[n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')]
    assert len(nodes)==1
    old=nodes[0];check=inspect(old.path());assert check['passed']
    plan=preflight(old.userData('workai_instance_id'))
    assert not plan['ready'] and 'Recipe version changed' in str(plan['errors'])
    report['legacy'].append(dict(hip=hip,geometry_sha256=check['geometry_sha256'],inspect_passed=True,update_rejected=True))
report['passed']=True;(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
