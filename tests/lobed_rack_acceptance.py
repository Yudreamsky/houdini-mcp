"""Fresh hython: isolated native body/bolt check, then saved-rack integration."""
import hashlib,json,math,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local import lobed_rack_geometry as builder,lobed_checks,rack_inspection,assembly_checks
from houdini_mcp_local.procedural_assets import upsert,preflight
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty hython')
folder=ROOT/'assets/repeated-rack-v01/default-01';hip=folder/'sample.hip';spec=json.loads((folder/'instance.json').read_text());filehash=hashlib.sha256(hip.read_bytes()).hexdigest()
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

# Pass through native Houdini polygon storage before inspecting the independent part.
p=builder.validate({});raw=builder.blue_body(p['diameter_3'],p['wall_3'],int(p['bolt_count']),int(p['segments']),p['blue_lobe_depth'],p['joint_offset_3'],.044+p['diameter_3']/2,p['spacing_23'])
prototype=hou.Geometry();prototype.addAttrib(hou.attribType.Prim,'name','');prototype.addAttrib(hou.attribType.Prim,'part_type','')
points=[]
for q in raw['points']:
    pt=prototype.createPoint();pt.setPosition(q);points.append(pt)
for f in raw['faces']:
    prim=prototype.createPolygon()
    for i in f:prim.addVertex(points[i])
    prim.setAttribValue('name',raw['name']);prim.setAttribValue('part_type',raw['kind'])
bolts=[v for v in extract(old.geometry()) if v['name'].startswith('pipe3_bolt_') and v['kind']=='bolt']
isolated=lobed_checks.measure(extract(prototype)+bolts,p);assert isolated['passed'],isolated
created=upsert('lobed-rack-hom',recipe='pipe_rack_lobed');node=hou.node(created['path']);assert created['check']['passed']
assert baseline['world_transform']==created['check']['world_transform']
after=assembly_checks.fingerprints(node.geometry());diff=assembly_checks.compare(before,after)
assert len(diff['unchanged'])==204 and diff['changed']==['pipe3_gasket'] and not diff['removed'] and not diff['added'],diff
negatives={};cy=.044+p['diameter_3']/2;cz=p['spacing_23']
for action in ('shift','rotate','blocked_bore','blocked_bolt'):
    geo=hou.Geometry();geo.merge(node.geometry())
    ids={v.point().number() for prim in geo.prims() if prim.attribValue('name')=='pipe3_gasket' for v in prim.vertices()}
    if action in ('shift','rotate'):
        for point in geo.points():
            if point.number() not in ids:continue
            x,y,z=point.position()
            if action=='shift':point.setPosition((x+.02,y,z))
            else:
                a=math.pi/p['bolt_count'];y-=cy;z-=cz;point.setPosition((x,cy+y*math.cos(a)-z*math.sin(a),cz+y*math.sin(a)+z*math.cos(a)))
    else:
        center_y=cy+(.635*p['diameter_3'] if action=='blocked_bolt' else 0);extent=.02
        prim=geo.createPolygon()
        for y,z in [(-extent,-extent),(extent,-extent),(extent,extent),(-extent,extent)]:
            pt=geo.createPoint();pt.setPosition((p['joint_offset_3'],center_y+y,cz+z));prim.addVertex(pt)
        prim.setAttribValue('name','pipe3_gasket');prim.setAttribValue('part_type','gasket')
    check=rack_inspection.inspect(node,geo);assert not check['passed'],action;negatives[action]=check['issues']
    if action in ('rotate','blocked_bolt'):assert 'Bolt intersects or fails to span blue body hole' in check['issues']
    if action=='blocked_bore':assert 'Blue body axial bore obstructed/off axis' in check['issues']
invalid=preflight('lobed-rack-hom',{'diameter_3':.6,'spacing_23':.73});assert not invalid['ready']
assert assembly_checks.fingerprints(node.geometry())==after
updated=upsert('lobed-rack-hom',{'blue_lobe_depth':.12});assert updated['check']['passed']
update_diff=assembly_checks.compare(after,assembly_checks.fingerprints(node.geometry()));assert update_diff['changed']==['pipe3_gasket'] and len(update_diff['unchanged'])==204
reset=upsert('lobed-rack-hom',created['parameters']);assert reset['check']['geometry_sha256']==created['check']['geometry_sha256']
assert hashlib.sha256(hip.read_bytes()).hexdigest()==filehash
report=dict(passed=True,independent_native_body=isolated,baseline_hash=baseline['geometry_sha256'],world_transform_unchanged=True,check=created['check'],part_diff=diff,negatives=negatives,invalid_preflight=invalid,depth_update_diff=update_diff,source_unchanged=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':True,'parts':created['check']['part_count'],'unchanged':len(diff['unchanged']),'blue':created['check']['measurements']['lobed_body']['measurements']}))
