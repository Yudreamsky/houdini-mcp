"""Native three-joint replacement and six-flange finish against saved baselines."""
import json,sys,hashlib
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from houdini_mcp_local import all_pad_checks,assembly_checks,rack_inspection
from houdini_mcp_local.procedural_assets import upsert,preflight
import finish_flange_edges as finish
out=Path(sys.argv[1]).resolve();out.mkdir(exist_ok=False,parents=True)
folder=ROOT/'assets/flange-bevel-v02';spec=json.loads((folder/'instance.json').read_text());hip=folder/'after.hip';h=hashlib.sha256(hip.read_bytes()).hexdigest()
hou.hipFile.load(str(hip),suppress_save_prompt=True)
old=hou.node(spec['source_instance']['path']);old_finish=hou.node(spec['finishing']['output'])
baseline=finish.verify(old.path(),old_finish.path());assert baseline['passed']
before=assembly_checks.fingerprints(old.geometry());before_finished=assembly_checks.fingerprints(old_finish.geometry())
created=upsert('all-pads-hom',recipe='pipe_rack_all_pads');node=hou.node(created['path']);assert created['check']['passed']
after=assembly_checks.fingerprints(node.geometry());diff=assembly_checks.compare(before,after)
assert len(diff['unchanged'])==210 and not diff['changed'] and diff['removed']==['pipe2_gasket','pipe3_joint_b_gasket'] and len(diff['added'])==16,diff
setup=finish.build(node.path());finished=finish.verify(node.path(),setup['output']);assert finished['passed']
finaldiff=assembly_checks.compare(before_finished,assembly_checks.fingerprints(hou.node(setup['output']).geometry()))
assert len(finaldiff['unchanged'])==206 and finaldiff['changed']==['pipe2_flange_left','pipe2_flange_right','pipe3_joint_b_flange_left','pipe3_joint_b_flange_right'] and len(finaldiff['added'])==16 and len(finaldiff['removed'])==2,finaldiff
assert created['check']['world_transform']==baseline['inspection']['world_transform']
def extract(geo):
    parts={}
    for prim in geo.prims():
        name=prim.attribValue('name');part=parts.setdefault(name,dict(name=name,kind=prim.attribValue('part_type'),points=[],faces=[],lookup={}))
        face=[]
        for vertex in prim.vertices():
            point=vertex.point();key=point.number()
            if key not in part['lookup']:part['lookup'][key]=len(part['points']);part['points'].append(tuple(point.position()))
            face.append(part['lookup'][key])
        part['faces'].append(face)
    return list(parts.values())
negatives={}
for prefix in ('pipe2_','pipe3_','pipe3_joint_b_'):
    geo=hou.Geometry();geo.merge(node.geometry());name=prefix+'pad_00'
    ids={v.point().number() for prim in geo.prims() if prim.attribValue('name')==name for v in prim.vertices()}
    for point in geo.points():
        if point.number() in ids:
            x,y,z=point.position();point.setPosition((x,y+.02,z))
    r=all_pad_checks.measure(extract(geo),created['parameters']);assert not r['passed'];negatives[prefix+'offset']=r['issues']
geo=hou.Geometry();geo.merge(node.geometry());geo.deletePrims([p for p in geo.prims() if p.attribValue('name')=='pipe3_joint_b_pad_07'],False)
r=all_pad_checks.measure(extract(geo),created['parameters']);assert not r['passed'];negatives['missing_last_pad']=r['issues']
invalid=preflight('all-pads-hom',{'spacing_23':.48});assert not invalid['ready']
grown=upsert('all-pads-hom',{'diameter_2':.30,'diameter_3':.32,'spacing_12':.65,'spacing_23':.65,'pad_radius_ratio':.12});hou.node(setup['output']).cook(force=True)
growth_finish=finish.verify(node.path(),setup['output']);assert growth_finish['passed']
reset=upsert('all-pads-hom',created['parameters']);hou.node(setup['output']).cook(force=True)
reset_finish=finish.verify(node.path(),setup['output']);assert reset_finish['inspection']['geometry_sha256']==finished['inspection']['geometry_sha256']
assert hashlib.sha256(hip.read_bytes()).hexdigest()==h
report=dict(passed=True,created=created,base_diff=diff,finished=finished,finished_diff=finaldiff,negative_cases=negatives,invalid_preflight=invalid,growth_passed=True,reset_passed=True,world_transform_unchanged=True,source_unchanged=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(passed=True,parts=created['check']['part_count'],pads=created['check']['measurements']['all_rubber_pads']['pad_count'],finished_unchanged=len(finaldiff['unchanged']),finished_changed=finaldiff['changed'])))
