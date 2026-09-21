"""Fresh hython: rack_acceptance.py OUTPUT [UNCHANGED_STRAIGHT_HIP ELBOW_HIP]."""
import json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local import rack_inspection,sample_inspection

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty headless process')
report={'passed':False,'negative':{},'unchanged_existing':[]}
first=upsert('rack-hom',recipe='pipe_rack_sample');node=hou.node(first['path'])
assert first['check']['passed'] and first['check']['part_count']==191
report['default']=first['check']['measurements']
for case in ('missing_seat','shifted_pipe','missed_hole'):
    g=hou.Geometry();g.merge(node.geometry())
    if case=='missing_seat':g.deletePrims([v for v in g.prims() if v.attribValue('name')=='rack_pos_0_pipe2_seat'],False)
    else:
        ids={v.point().number() for prim in g.prims() if (prim.attribValue('name').startswith('pipe2_') if case=='shifted_pipe' else prim.attribValue('name')=='rack_pos_0_pipe2_clamp') for v in prim.vertices()}
        for point in g.points():
            if point.number() in ids:
                x,y,z=point.position();point.setPosition((x,y+.025,z-.45) if case=='shifted_pipe' else (x+.012,y,z))
    check=rack_inspection.inspect(node,g);assert not check['passed'],case
    report['negative'][case]=check['issues']
before={k:node.evalParm(k) for k in first['parameters']}
bad=preflight('rack-hom',{'spacing_12':.2});assert not bad['ready'] and any(e['code']=='flange_clearance_12' for e in bad['errors'])
assert before=={k:node.evalParm(k) for k in before}
grown=upsert('rack-hom',{'length':3.6,'rise_2':0,'rise_3':.2})
assert grown['recipe']=='pipe_rack_sample' and grown['check']['passed'] and grown['check']['measurements']['support_count']==4
assert upsert('rack-hom',first['parameters'])['check']['geometry_sha256']==first['check']['geometry_sha256']
report['geometry_sha256']=first['check']['geometry_sha256']
for hip in sys.argv[2:]:
    hou.hipFile.load(str(Path(hip).resolve()),suppress_save_prompt=True)
    nodes=[n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')];assert len(nodes)==1
    old=nodes[0];check=sample_inspection.inspect(old.path());assert check['passed']
    plan=preflight(old.userData('workai_instance_id'));assert plan['ready'] and not plan['would_change']
    same=upsert(old.userData('workai_instance_id'));assert not same['changed'] and same['check']['geometry_sha256']==check['geometry_sha256']
    report['unchanged_existing'].append(dict(hip=hip,geometry_sha256=check['geometry_sha256'],no_op=True))
report['passed']=True;(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
