"""Fresh hython: compare candidate against saved v0.10 asset and inject neighbor faults."""
import hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight
from houdini_mcp_local import rack_inspection,assembly_checks
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use a fresh empty hython')
folder=ROOT/'assets/pipe-reference-v01/default-02';hip=folder/'sample.hip';oldspec=json.loads((folder/'instance.json').read_text());before_file=hashlib.sha256(hip.read_bytes()).hexdigest()
hou.hipFile.load(str(hip),suppress_save_prompt=True);old=hou.node(oldspec['path']);baseline=rack_inspection.inspect(old)
assert baseline['passed'] and baseline['geometry_sha256']==oldspec['geometry_sha256']
before=assembly_checks.fingerprints(old.geometry())
created=upsert('coupled-rack-hom',recipe='pipe_rack_coupled');node=hou.node(created['path']);assert created['check']['passed']
assert baseline['world_transform']==created['check']['world_transform']
after=assembly_checks.fingerprints(node.geometry());diff=assembly_checks.compare(before,after)
assert len(diff['unchanged'])==142 and diff['changed']==['pipe1_pipe_left','pipe1_pipe_right'],diff
assert len(diff['removed'])==43 and len(diff['added'])==17
assert all(n.startswith('pipe1_') for kind in ('removed','added','changed') for n in diff[kind])
negatives={}
for name,group in [('rack_pos_0_pipe1_clamp','u_bolts'),('rack_pos_0_web','channels')]:
    geo=hou.Geometry();geo.merge(node.geometry())
    ids={v.point().number() for prim in geo.prims() if prim.attribValue('name')==name for v in prim.vertices()}
    for point in geo.points():
        if point.number() in ids:
            x,y,z=point.position();point.setPosition((x-.38,y,z))
    check=rack_inspection.inspect(node,geo);assert not check['passed'] and any('clearance below margin: '+group in str(v) for v in check['issues'])
    negatives[name]=check['issues']
geo=hou.Geometry();geo.merge(node.geometry());prim=next(p for p in geo.prims() if p.attribValue('name')=='pipe2_pipe_left');prim.setAttribValue('Cd',(1.,0.,0.))
color_change=assembly_checks.compare(after,assembly_checks.fingerprints(geo));assert color_change['changed']==['pipe2_pipe_left']
bad=preflight('coupled-rack-hom',{'diameter_1':.1,'support_pitch':.8,'joint_offset_1':.29,'red_shell_width':.16});assert not bad['ready']
assert assembly_checks.fingerprints(node.geometry())==after
assert hashlib.sha256(hip.read_bytes()).hexdigest()==before_file
report=dict(passed=True,baseline_hip=str(hip),baseline_hash=baseline['geometry_sha256'],baseline_world_transform=baseline['world_transform'],world_transform_unchanged=True,check=created['check'],part_diff=diff,before_fingerprints=before,after_fingerprints=after,negatives=negatives,color_change_detection=color_change,invalid_preflight=bad,source_unchanged=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'parts':created['check']['part_count'],'unchanged':len(diff['unchanged']),'clearance':created['check']['measurements']['coupling_neighbors']}))
