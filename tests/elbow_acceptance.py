"""Fresh hython: elbow_acceptance.py NEW_OUTPUT_DIR (real HOM, not MCP/GUI)."""
import hashlib,json,shutil,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,catalog
from houdini_mcp_local.sample_inspection import inspect
from houdini_mcp_local.elbow_inspection import inspect as inspect_route

out=Path(sys.argv[1]).resolve()
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty headless hython')
if out.exists():raise FileExistsError('Use new output directory')
out.mkdir(parents=True)
straight=upsert('straight-regression');assert straight['check']['passed'] and straight['check']['measurements']['support_style']=='u_bolt_v1'
assert len(catalog()['recipes'])==2
first=upsert('elbow-test',recipe='pipe_elbow_sample');node=hou.node(first['path'])
assert first['check']['passed'] and first['check']['measurements']['support_count']==4
again=upsert('elbow-test',recipe='pipe_elbow_sample');assert not again['created'] and not again['changed']
for kwargs in ({'parameters':{'diameter':.6,'bend_radius':.6},'recipe':'pipe_elbow_sample'}, {'recipe':'pipe_support_sample'}):
    try:upsert('elbow-test',**kwargs)
    except ValueError:pass
    else:raise AssertionError('Expected invalid input/recipe rejection')
assert inspect(node.path())['geometry_sha256']==first['check']['geometry_sha256']
# A shifted elbow is still closed and healthy; the interface check must catch it.
damaged=hou.Geometry();damaged.merge(node.geometry())
ids={v.point().number() for prim in damaged.prims() if prim.attribValue('name')=='elbow' for v in prim.vertices()}
for point in damaged.points():
    if point.number() in ids:point.setPosition(point.position()+hou.Vector3(.01,0,0))
negative=inspect_route(node,damaged)
assert not negative['passed'] and any('endpoint rings' in str(v) for v in negative['issues'])
grown=upsert('elbow-test',{'inlet_length':4.2,'outlet_length':3.6,'diameter':.5,'bend_radius':.9},recipe='pipe_elbow_sample')
assert grown['check']['passed'] and grown['check']['measurements']['support_count']==8
assert {p['name'] for p in first['check']['parts']} <= {p['name'] for p in grown['check']['parts']}
final=upsert('elbow-test',first['parameters'],recipe='pipe_elbow_sample')
library=out/Path(final['library']).name;shutil.copy2(final['library'],library)
hou.hda.installFile(str(library))
for definition in hou.hda.definitionsInFile(str(library)):definition.setIsPreferred(True)
# Keep the regression instance and its HDA dependency out of the delivery HIP.
hou.node(straight['object_path']).destroy()
hip=out/'elbow-sample.hip';hou.hipFile.save(str(hip));hou.hipFile.load(str(hip),suppress_save_prompt=True)
reopened=inspect(final['path']);assert reopened['passed'] and reopened['geometry_sha256']==first['check']['geometry_sha256']
report=dict(passed=True,mode='headless HOM, not MCP/GUI',houdini=hou.applicationVersionString(),
            path=final['path'],library=str(library),type=hou.node(final['path']).type().name(),hip=str(hip),
            parameters=final['parameters'],geometry_sha256=reopened['geometry_sha256'],part_count=reopened['part_count'],
            measurements=reopened['measurements'],negative_test=negative['issues'],straight_regression_sha256=straight['check']['geometry_sha256'])
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
