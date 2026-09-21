"""Fresh hython with a locally saved v0.12 baseline; no GUI state changes."""
import hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local import rack_inspection,assembly_checks
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty hython')
folder=ROOT/'assets/coupled-rack-v01/default-01';hip=folder/'sample.hip';spec=json.loads((folder/'instance.json').read_text());filehash=hashlib.sha256(hip.read_bytes()).hexdigest()
hou.hipFile.load(str(hip),suppress_save_prompt=True);old=hou.node(spec['path']);baseline=rack_inspection.inspect(old)
assert baseline['passed'] and baseline['geometry_sha256']==spec['geometry_sha256']
before=assembly_checks.fingerprints(old.geometry())
created=upsert('repeated-rack-hom',recipe='pipe_rack_repeated');node=hou.node(created['path']);assert created['check']['passed']
assert baseline['world_transform']==created['check']['world_transform']
after=assembly_checks.fingerprints(node.geometry());diff=assembly_checks.compare(before,after)
assert len(diff['unchanged'])==160 and diff['changed']==['pipe3_pipe_right'] and not diff['removed'] and len(diff['added'])==44,diff
negatives={}
for name,delta in [('pipe3_pipe_middle',.02),('pipe3_joint_b_gasket',.02),('pipe3_joint_b_bolt_00_shaft',.3),('rack_pos_0_web',.38)]:
    geo=hou.Geometry();geo.merge(node.geometry())
    ids={v.point().number() for prim in geo.prims() if prim.attribValue('name')==name for v in prim.vertices()};assert ids,name
    for point in geo.points():
        if point.number() in ids:
            x,y,z=point.position();point.setPosition((x+delta,y,z))
    check=rack_inspection.inspect(node,geo);assert not check['passed'],name;negatives[name]=check['issues']
geo=hou.Geometry();geo.merge(node.geometry());geo.deletePrims([v for v in geo.prims() if v.attribValue('name')=='pipe3_pipe_middle'],True)
missing=rack_inspection.inspect(node,geo);assert not missing['passed'];negatives['missing_middle']=missing['issues']
invalid=[]
for values in ({'second_joint_offset_3':.6},{'second_joint_offset_3':1.35},{'second_joint_offset_3':.35,'joint_offset_3':.3}):
    result=preflight('repeated-rack-hom',values);assert not result['ready'];invalid.append(result)
assert assembly_checks.fingerprints(node.geometry())==after
moved=upsert('repeated-rack-hom',{'second_joint_offset_3':1.1});assert moved['check']['passed']
movement=assembly_checks.compare(after,assembly_checks.fingerprints(node.geometry()))
assert not movement['added'] and not movement['removed']
assert all(n.startswith('pipe3_joint_b_') or n in ('pipe3_pipe_middle','pipe3_pipe_right') for n in movement['changed'])
reset=upsert('repeated-rack-hom',created['parameters']);assert reset['check']['geometry_sha256']==created['check']['geometry_sha256']
assert hashlib.sha256(hip.read_bytes()).hexdigest()==filehash
report=dict(passed=True,baseline_hip=str(hip),baseline_hash=baseline['geometry_sha256'],world_transform_unchanged=True,
            check=created['check'],part_diff=diff,before_fingerprints=before,after_fingerprints=after,negatives=negatives,invalid_preflight=invalid,
            second_joint_update_diff=movement,reset_hash=reset['check']['geometry_sha256'],source_unchanged=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'parts':created['check']['part_count'],'unchanged':len(diff['unchanged']),'chain':created['check']['measurements']['repeated_chain']}))
