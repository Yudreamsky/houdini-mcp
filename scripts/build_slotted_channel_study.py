"""Build a separate photo-guided C-channel HIP using hython. No GUI mutation."""
import argparse,hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,help='New output directory; existing paths are rejected')
OUT=Path(parser.parse_args().output).resolve()
OUT.mkdir(parents=True,exist_ok=False)
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import slotted_channel_sample as sample
from houdini_mcp_local.pad_checks import topology
import ast
setup_tree=ast.parse((ROOT/'scripts/accept_asset.py').read_text())
setup_function=next(n for n in setup_tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_setup')
exec(compile(ast.Module(body=[setup_function],type_ignores=[]),'<render_setup>','exec'))

hou.hipFile.clear(suppress_save_prompt=True)
obj=hou.node('/obj').createNode('geo','S1_channel_study')
for child in obj.children():child.destroy()
src=obj.createNode('python','channel_parameters')
for name,value in sample.DEFAULTS.items():
    src.addSpareParmTuple(hou.FloatParmTemplate(name,name.replace('_',' ').title()+' (m)',1,default_value=(value,)))
src.parm('python').set((ROOT/'scripts/slotted_channel_sample.py').read_text()+'\ncook(hou.pwd())\n')
edge=obj.createNode('python','physical_edges');edge.setInput(0,src)
edge.parm('python').set('''import hou,math
g=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())
group=g.createEdgeGroup('physical_edges');adj={};lookup={}
for prim in g.prims():
 for edge in prim.edges():
  key=tuple(sorted(p.number() for p in edge.points()));adj.setdefault(key,[]).append(prim.normal());lookup[key]=edge
for key,normals in adj.items():
 if len(normals)==2 and normals[0].dot(normals[1])<math.cos(math.radians(30)):group.add(lookup[key])
''')
bevel=obj.createNode('polybevel::3.0','edge_softening');bevel.setInput(0,edge)
bevel.parm('group').set('physical_edges');bevel.parm('grouptype').set(2)
bevel.parm('offset').set(.00018);bevel.parm('divisions').set(2);bevel.parm('filletshape').set(4)
bevel.parm('useedgefilletgroup').set(1);bevel.parm('edgeprims').set('edge_roundovers')
normal=obj.createNode('normal','vertex_normals');normal.setInput(0,bevel)
normal.parm('type').set(1);normal.parm('cuspangle').set(60)
flat=obj.createNode('python','preserve_flat_planes');flat.setInput(0,normal)
flat.parm('python').set('''import hou
g=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())
rounded={p.number() for p in g.findPrimGroup('edge_roundovers').prims()}
for prim in g.prims():
 normal=prim.normal()
 if prim.number() not in rounded and max(abs(v) for v in normal)>.999999:
  for vertex in prim.vertices():vertex.setAttribValue('N',normal)
''')
out=obj.createNode('null','OUT_CHANNEL');out.setInput(0,flat);out.setDisplayFlag(True);out.setRenderFlag(True)
obj.layoutChildren()

def check(node):
 node.cook(force=True);assert not node.errors(),node.errors();g=node.geometry()
 data={'points':[list(p.position()) for p in g.points()], 'faces':[[v.point().number() for v in f.vertices()] for f in g.prims()]}
 result=topology(data);spec=json.loads(g.attribValue('channel_spec'));count=len(spec['slot_centers'])
 assert result['closed'] and result['components']==1 and result['signed_volume']>0 and result['euler']==2-2*count,result
 p=spec['parameters'];hits=[]
 for z in spec['slot_centers']:
  hit=g.intersect(hou.Vector3(0,p['depth']+.05,z),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3())
  assert hit==-1,('Blocked actual slot',z,hit);hits.append(hit)
 z=(spec['slot_centers'][0]+spec['slot_centers'][1])/2
 assert g.intersect(hou.Vector3(0,p['depth']+.05,z),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3())>=0,'Missing web between holes'
 assert g.intersect(hou.Vector3(0,p['depth']/2,z),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3())==-1,'Closed channel opening'
 result.update(slot_count=count,slot_rays_clear=True,web_bridge_present=True,open_section_verified=True,
               points=len(data['points']),faces=len(data['faces']),sha=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest())
 if g.findVertexAttrib('N'):
  rounded={f.number() for f in g.findPrimGroup('edge_roundovers').prims()}
  deviations=[(hou.Vector3(v.attribValue('N'))-f.normal()).length() for f in g.prims() if f.number() not in rounded and max(abs(a) for a in f.normal())>.999999 for v in f.vertices()]
  result['max_planar_normal_error']=max(deviations);assert max(deviations)<1e-6
  result['normal_sha']=hashlib.sha256(json.dumps([list(v.attribValue('N')) for f in g.prims() for v in f.vertices()]).encode()).hexdigest()
 return result

report={'base':check(src),'finished':check(out)}
# Deliberately cover a slot in a detached geometry copy to check the ray oracle.
bad=hou.Geometry();bad.merge(out.geometry());poly=bad.createPolygon();p=sample.DEFAULTS;z=json.loads(bad.attribValue('channel_spec'))['slot_centers'][0]
for x,zz in [(-.01,z-.02),(.01,z-.02),(.01,z+.02),(-.01,z+.02)]:
 q=bad.createPoint();q.setPosition((x,p['depth'],zz));poly.addVertex(q)
assert bad.intersect(hou.Vector3(0,p['depth']+.05,z),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3())>=0
report['filled_slot_counterexample_detected']=True
src.parm('length').set(1.47);src.parm('width').set(.052)
report['grown']=check(out)
src.parm('slot_length').set(.059)
try:src.cook(force=True)
except hou.OperationFailed:pass
assert src.errors(),'Invalid slot overlap not rejected';report['invalid_rejected']=list(src.errors())
for name,value in sample.DEFAULTS.items():src.parm(name).set(value)
report['reset']=check(out);assert report['reset']['sha']==report['finished']['sha']
assert report['reset']['normal_sha']==report['finished']['normal_sha']
original=obj.worldTransform();obj.parmTuple('r').set((31,47,-12));obj.parmTuple('t').set((.4,1.2,-.6))
assert check(out)['sha']==report['finished']['sha'];report['rotation_translation_preserve_local_geometry']=True
obj.setWorldTransform(original)
exec(render_setup(out.path()))
mat=hou.node('/mat/accept_material');mat.parm('basecolor_usePointColor').set(0)
mat.parmTuple('basecolor').set((.48,.52,.56));mat.parm('metallic').set(.8);mat.parm('rough').set(.30)
hou.node('/obj/key').parm('light_intensity').set(7);hou.node('/obj/fill').parm('light_intensity').set(4)
def aim(n,target,offset):
 target=hou.Vector3(target);eye=target+hou.Vector3(offset);z=(eye-target).normalized();x=hou.Vector3(0,1,0).cross(z).normalized();y=z.cross(x)
 n.setWorldTransform(hou.Matrix4((x[0],x[1],x[2],0,y[0],y[1],y[2],0,z[0],z[1],z[2],0,eye[0],eye[1],eye[2],1)))
for name,offset,size,power in [('strip',(0,1,0),(.3,1.2),1.1),('fill_strip',(1,-.4,-.4),(.5,1.0),1.2)]:
 light=hou.node('/obj').createNode('hlight::2.0',name);light.parm('light_type').set(2);light.parmTuple('areasize').set(size);light.parm('light_intensity').set(power);aim(light,(0,.02,0),offset if offset!=(0,1,0) else (.1,1,.1))
cam=hou.node('/obj/accept_camera');cam.parm('orthowidth').set(1.14);aim(cam,(0,.02,0),(.8,.9,.32))
hou.hipFile.save(str(OUT/'channel.hip'))
cam.parm('orthowidth').set(.36);aim(cam,(0,.02,.40),(.35,-.45,.8))
hou.hipFile.save(str(OUT/'open-end-detail.hip'))
cam.parm('orthowidth').set(.34);aim(cam,(0,.02,0),(.4,.9,.40))
hou.hipFile.save(str(OUT/'slot-detail.hip'))
hou.hipFile.load(str(OUT/'channel.hip'),suppress_save_prompt=True)
report['reopened']=check(hou.node('/obj/S1_channel_study/OUT_CHANNEL'));assert report['reopened']['sha']==report['finished']['sha']
assert report['reopened']['normal_sha']==report['finished']['normal_sha']
report['passed']=True;report['scope']='Independent S1 study only; not assembled into rack'
(OUT/'hom-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
