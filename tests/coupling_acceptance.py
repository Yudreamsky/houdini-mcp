"""Fresh hython: actual mesh negatives, protected preflight and old recipe identity."""
import json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local.coupling_inspection import inspect
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty hython')
first=upsert('coupling-hom',recipe='external_coupling_sample',parameters={'clocking':0});node=hou.node(first['path'])
assert first['check']['passed'] and first['check']['part_count']==19
negatives={}
for name,axis,message in [('pipe_right',1,'Pipe off axis'),('housing_upper',0,'Housing axial alignment'),('bolt_1',2,'Bolt misses')]:
    geo=hou.Geometry();geo.merge(node.geometry())
    ids={v.point().number() for p in geo.prims() if p.attribValue('name')==name for v in p.vertices()}
    for point in geo.points():
        if point.number() in ids:
            q=list(point.position());q[axis]+=.02;point.setPosition(q)
    result=inspect(node,geo);assert not result['passed'] and any(message in e for e in result['issues']),result
    negatives[name]=result['issues']
bad=preflight('coupling-hom',{'length':.4,'joint_offset':.2});assert not bad['ready']
assert inspect(node)['geometry_sha256']==first['check']['geometry_sha256']
old=upsert('reference-regression',recipe='pipe_rack_reference');assert old['check']['passed']
assert old['check']['geometry_sha256']=='f0b7052ea2af278d5ee6f2e8188c47a32e4903d7d34d22192d8b49a120363764'
report=dict(passed=True,check=first['check'],negatives=negatives,invalid_preflight=bad,old_reference_hash=old['check']['geometry_sha256'])
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'parts':first['check']['part_count'],'negatives':list(negatives)}))
