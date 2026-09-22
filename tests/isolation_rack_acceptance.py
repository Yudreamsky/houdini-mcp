"""Fresh native Houdini acceptance against the actual saved v0.14 asset."""
import hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local import isolated_rack_geometry as builder,pad_checks,rack_inspection,assembly_checks
from houdini_mcp_local.procedural_assets import upsert,preflight,source
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty hython')
folder=ROOT/'assets/lobed-rack-v01/default-01';hip=folder/'sample.hip';spec=json.loads((folder/'instance.json').read_text());filehash=hashlib.sha256(hip.read_bytes()).hexdigest()
hou.hipFile.load(str(hip),suppress_save_prompt=True);old=hou.node(spec['path']);baseline=rack_inspection.inspect(old)
assert baseline['passed'] and baseline['geometry_sha256']==spec['geometry_sha256']
before=assembly_checks.fingerprints(old.geometry())

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

created=upsert('isolation-rack-hom',recipe='pipe_rack_isolated');node=hou.node(created['path']);assert created['check']['passed']
assert baseline['world_transform']==created['check']['world_transform']
after=assembly_checks.fingerprints(node.geometry());diff=assembly_checks.compare(before,after)
assert len(diff['unchanged'])==204 and not diff['changed'] and diff['removed']==['pipe3_gasket'] and len(diff['added'])==8,diff
native=extract(node.geometry());p=created['parameters']
# Inspect the first assembly in isolation, including actual contact flanges.
selected=[v for v in native if v['name'].startswith('pipe3_pad_') or v['name'].startswith('pipe3_bolt_') or v['name'] in ('pipe3_flange_left','pipe3_flange_right')]
isolated=pad_checks.measure(selected,p);assert isolated['passed'],isolated
negatives={}
for action in ('axial_gap','axis','missing','blocked_hole','continuous'):
    geo=hou.Geometry();geo.merge(node.geometry())
    prims=[v for v in geo.prims() if v.attribValue('name')=='pipe3_pad_00'];ids={v.point().number() for prim in prims for v in prim.vertices()}
    if action in ('axial_gap','axis'):
        for point in geo.points():
            if point.number() in ids:
                q=list(point.position());q[0 if action=='axial_gap' else 1]+=.02;point.setPosition(q)
    elif action=='missing':geo.deletePrims(prims,False)
    elif action=='continuous':
        extra=hou.Geometry();extra.merge(old.geometry());extra.deletePrims([v for v in extra.prims() if v.attribValue('name')!='pipe3_gasket'],False);geo.merge(extra)
    else:
        cy=.044+p['diameter_3']/2+.635*p['diameter_3'];cz=p['spacing_23'];prim=geo.createPolygon()
        for y,z in [(-.02,-.02),(.02,-.02),(.02,.02),(-.02,.02)]:
            pt=geo.createPoint();pt.setPosition((p['joint_offset_3'],cy+y,cz+z));prim.addVertex(pt)
        prim.setAttribValue('name','pipe3_pad_00');prim.setAttribValue('part_type','rubber_pad')
    check=rack_inspection.inspect(node,geo);assert not check['passed'],action;negatives[action]=check['issues']
invalid=preflight('isolation-rack-hom',{'bolt_count':16});assert not invalid['ready']
assert assembly_checks.fingerprints(node.geometry())==after
updated=upsert('isolation-rack-hom',{'pad_radius_ratio':.12});assert updated['check']['passed']
update_diff=assembly_checks.compare(after,assembly_checks.fingerprints(node.geometry()));assert len(update_diff['changed'])==8 and len(update_diff['unchanged'])==204
reset=upsert('isolation-rack-hom',created['parameters']);assert reset['check']['geometry_sha256']==created['check']['geometry_sha256']
assert hashlib.sha256(hip.read_bytes()).hexdigest()==filehash
report=dict(passed=True,independent_native_pads=isolated,baseline_geometry_valid_but_construction_interpretation_withdrawn=True,baseline_hash=baseline['geometry_sha256'],world_transform_unchanged=True,check=created['check'],part_diff=diff,negatives=negatives,invalid_preflight=invalid,radius_update_diff=update_diff,source_unchanged=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'parts':created['check']['part_count'],'unchanged':len(diff['unchanged']),'pad_count':isolated['measurements']['pad_count']}))
