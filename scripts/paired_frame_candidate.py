"""Paired uprights / T1 end-joint visual candidate. No bracket/anchor or load-path claim.

Run with hython and explicit saved sources; always write a new output directory.
The original locked HDA and the finishing chain remain intact.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import hou

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.assembly_checks import compare,separation
from houdini_mcp_local.pad_checks import topology

STATION='rack_pos_0'
RETIRED=tuple(STATION+s for side in (-1,1) for s in (f'_rod_{side}',f'_anchor_{side}',f'_nut_{side}_0.031',f'_nut_{side}_0.044'))
HOST=STATION+'_lip_1'
FRAME='/obj/S1_channel_study'

PLACEMENT_CODE='''import hou,json
n=hou.pwd();g=n.geometry();g.clear();g.merge(n.inputs()[0].geometry())
host=n.inputs()[1].geometry();side=SIDE_VALUE
rod=[v.point().position() for p in host.prims() if p.attribValue('name')=='rack_pos_0_rod_'+str(side) for v in p.vertices()]
x=(min(p[0] for p in rod)+max(p[0] for p in rod))/2
z=(min(p[2] for p in rod)+max(p[2] for p in rod))/2-side*.020
box=g.boundingBox();depth=box.maxvec()[1];lo=box.minvec()[2];hi=box.maxvec()[2]
gap=n.evalParm('contact_gap');bottom=n.evalParm('bottom');offset=n.evalParm('lateral_offset')
if side<0:matrix=hou.Matrix4((1,0,0,0, 0,0,1,0, 0,-1,0,0, x+offset,bottom+hi,z-depth-gap,1))
else:matrix=hou.Matrix4((1,0,0,0, 0,0,-1,0, 0,1,0,0, x+offset,bottom-lo,z+depth+gap,1))
g.transform(matrix)
for p in g.prims():p.setAttribValue('name','frame_redside' if side<0 else 'frame_blackside')
g.addAttrib(hou.attribType.Global,'placement_status','')
g.setGlobalAttribValue('placement_status',json.dumps(dict(status='T_end_joint_candidate',side=side,hidden_fastening='unmodeled',building_host='unknown',matrix=list(matrix.asTuple())),sort_keys=True))
'''


def bounds(g):
 b=g.boundingBox();return [list(b.minvec()),list(b.maxvec())]


def part(g,name):
 selected=hou.Geometry();selected.merge(g)
 selected.deletePrims([p for p in selected.prims() if p.attribValue('name')!=name])
 assert selected.prims(),'Missing actual component '+name
 return selected


def detailed(g):
 records={}
 for p in g.prims():
  records.setdefault(p.attribValue('name'),[]).append([p.attribValue('part_type'),p.attribValue('Cd'),
   p.attribValue('shop_materialpath') if g.findPrimAttrib('shop_materialpath') else None,
   [(list(v.point().position()),list(v.attribValue('N')) if g.findVertexAttrib('N') else None) for v in p.vertices()]])
 return {k:hashlib.sha256(json.dumps(v).encode()).hexdigest() for k,v in records.items()}


def inspect(rack,frame):
 issues=[];beam=hou.Geometry();beam.merge(rack)
 beam.deletePrims([p for p in beam.prims() if p.attribValue('name') not in (STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1')])
 bb=bounds(beam);fb=bounds(frame);side=json.loads(frame.attribValue('placement_status'))['side']
 plane=bb[0 if side<0 else 1][2]
 gap=(plane-fb[1][2]) if side<0 else (fb[0][2]-plane)
 if abs(gap)>3e-6:issues.append('T end face is floating or penetrating')
 xs=[bb[0][0]+(bb[1][0]-bb[0][0])*(i+.5)/13 for i in range(13)]
 ys=[.001,.003,.006,.020,.038,.041,.043];contacts=[]
 for x in xs:
  for y in ys:
   a=hou.Vector3();b=hou.Vector3()
   ia=beam.intersect(hou.Vector3(x,y,plane+side*.001),hou.Vector3(0,0,-side),a,hou.Vector3(),hou.Vector3(),min_hit=1e-7,max_hit=.004,tolerance=1e-7)
   ib=frame.intersect(hou.Vector3(x,y,plane-side*.001),hou.Vector3(0,0,side),b,hou.Vector3(),hou.Vector3(),min_hit=1e-7,max_hit=.004,tolerance=1e-7)
   if ia>=0 and ib>=0 and abs(a[2]-plane)<3e-6 and abs(b[2]-plane)<3e-6:contacts.append([x,y])
 if len(contacts)<6:issues.append('Insufficient actual end-face contact samples')
 boxes={}
 for prim in rack.prims():
  name=prim.attribValue('name');box=boxes.setdefault(name,[[float('inf')]*3,[-float('inf')]*3])
  for vertex in prim.vertices():
   q=vertex.point().position()
   for axis in range(3):box[0][axis]=min(box[0][axis],q[axis]);box[1][axis]=max(box[1][axis],q[axis])
 neighbors=[(separation(fb,b),name) for name,b in boxes.items() if name not in (STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1')]
 nearest=min(neighbors)
 if nearest[0]<.001:issues.append('Neighbor clearance cannot be proven')
 data=dict(points=[list(p.position()) for p in frame.points()],faces=[[v.point().number() for v in p.vertices()] for p in frame.prims()])
 top=topology(data);count=len(json.loads(frame.attribValue('channel_spec'))['slot_centers'])
 if not top['closed'] or top['components']!=1 or top['euler']!=2-2*count:issues.append('Frame topology mismatch')
 return dict(passed=not issues,issues=issues,side=side,joint='T_end_to_face',signed_end_gap=gap,contact_samples=len(contacts),tested_samples=91,contact_xy=contacts,beam_bounds=bb,frame_bounds=fb,nearest_neighbor=dict(name=nearest[1],aabb_clearance_lower_bound=nearest[0]),topology=top,role='Beam ends between continuous uprights; hidden fasteners and upper anchorage unmodeled')


def verify_crossarm(rack):
 import math
 report={}
 for name in (STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1'):
  g=part(rack,name);t=topology(dict(points=[list(p.position()) for p in g.points()],faces=[[v.point().number() for v in p.vertices()] for p in g.prims()]))
  assert t['closed'] and t['components']==1 and t['signed_volume']>0,t;report[name]=t
 web=part(rack,STATION+'_web');rays=0
 for i in (1,2,3):
  clamp=part(rack,STATION+f'_pipe{i}_clamp');b=bounds(clamp);radius=(b[1][0]-b[0][0])/2;x=(b[1][0]+b[0][0])/2
  for z in (b[0][2]+radius,b[1][2]-radius):
   for k in range(16):
    a=2*math.pi*k/16
    hit=web.intersect(hou.Vector3(x+radius*math.cos(a),.055,z+radius*math.sin(a)),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3(),min_hit=1e-7,max_hit=.025,tolerance=1e-7)
    assert hit==-1,('U-leg hole obstructed',i,z,k);rays+=1
   hit=web.intersect(hou.Vector3(x+.009,.055,z),hou.Vector3(0,-1,0),hou.Vector3(),hou.Vector3(),hou.Vector3(),min_hit=1e-7,max_hit=.025,tolerance=1e-7)
   assert hit>=0,'Missing web around U-leg hole'
 return dict(closed_parts=report,u_leg_clear_rays=rays,web_adjacent_to_holes_present=True)


def aim(n,target,offset):
 target=hou.Vector3(target);eye=target+hou.Vector3(offset);z=(eye-target).normalized();x=hou.Vector3(0,1,0).cross(z).normalized();y=z.cross(x)
 n.setWorldTransform(hou.Matrix4((x[0],x[1],x[2],0,y[0],y[1],y[2],0,z[0],z[1],z[2],0,eye[0],eye[1],eye[2],1)))


def build(args):
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
 sources={str(Path(p).resolve()):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (args.rack,args.channel)}
 hou.hipFile.load(str(Path(args.rack).resolve()),suppress_save_prompt=True)
 asset=next(n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')=='pipe_rack_all_pads')
 parent=asset.parent();finished=parent.node('OUT_FINISHED')
 assert parent.worldTransform()==hou.hmath.identityTransform(),'Fixed sample requires identity rack placement'
 before=detailed(finished.geometry());assert set(RETIRED)<=set(before)
 original_material=parent.parm('shop_materialpath').eval()
 library=Path(asset.type().definition().libraryFilePath());delivery=out/library.name;shutil.copy2(library,delivery)
 hou.hda.installFile(str(delivery))
 for d in hou.hda.definitionsInFile(str(delivery)):d.setIsPreferred(True)
 assert asset.matchesCurrentDefinition()
 hou.hipFile.merge(str(Path(args.channel).resolve()),node_pattern=FRAME+'*',ignore_load_warnings=False)
 first=hou.node(FRAME);assert first and first.node('OUT_CHANNEL')
 second=hou.copyNodesTo((first,),hou.node('/obj'))[0];second.setName('S1_other_side',unique_name=False)
 steel=hou.node('/mat').createNode('principledshader::2.0','frame_galvanized')
 steel.parmTuple('basecolor').set((.48,.52,.56));steel.parm('basecolor_usePointColor').set(0);steel.parm('metallic').set(.8);steel.parm('rough').set(.30)
 retained=parent.createNode('python','retire_front_hanger_placeholders');retained.setInput(0,finished)
 retained.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\nretired='+repr(RETIRED+(STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1'))+'\ng.deletePrims([p for p in g.prims() if p.attribValue("name") in retired])')
 merged=parent.createNode('merge','trimmed_crossarm_and_retained');merged.setInput(0,retained)
 for k,name in enumerate((STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1'),1):
  selected=parent.createNode('python','select_crossarm_'+str(k));selected.setInput(0,finished)
  selected.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name")!='+repr(name)+'])')
  previous=selected
  for side in (-1,1):
   rod=part(finished.geometry(),STATION+f'_rod_{side}');b=bounds(rod);z=(b[0][2]+b[1][2])/2-side*.020
   clip=parent.createNode('clip','cut_'+str(k)+('_left' if side<0 else '_right'));clip.setInput(0,previous)
   clip.parmTuple('dir').set((0,0,-side));clip.parm('dist').set(-side*z);clip.parm('dofill').set(1);clip.parm('snaptol').set(1e-7);clip.parm('fillpolygons').set('new_end_caps');previous=clip
  caps=parent.createNode('normal','end_normals_'+str(k));caps.setInput(0,previous);caps.parm('group').set('new_end_caps');caps.parm('grouptype').set(4);caps.parm('type').set(1);caps.parm('cuspangle').set(0)
  original=next(p for p in selected.geometry().prims());attributes={a:original.attribValue(a) for a in ('name','part_type','Cd','shop_materialpath')}
  tags=parent.createNode('python','restore_beam_identity_'+str(k));tags.setInput(0,caps)
  tags.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\nvalues='+repr(attributes)+'\nfor p in g.prims():\n for key,value in values.items():p.setAttribValue(key,value)')
  merged.setInput(k,tags)
 rackout=parent.createNode('null','OUT_FRAME_CANDIDATE');rackout.setInput(0,merged);rackout.setDisplayFlag(True);rackout.setRenderFlag(True)
 frames=[];checks={};negative={};local_shas={}
 for frame,side in ((first,-1),(second,1)):
  assert max(abs(a-b) for a,b in zip(frame.worldTransform().asTuple(),hou.hmath.identityTransform().asTuple()))<1e-9,'Unexpected world transform on source channel'
  frame.parm('shop_materialpath').set(steel.path())
  frame.node('channel_parameters').parm('width').set(.049)
  local=frame.node('OUT_CHANNEL');local_shas[frame.path()]=detailed(local.geometry())
  host=frame.createNode('object_merge','actual_rack_host');host.parm('objpath1').set(finished.path());host.parm('xformtype').set(1)
  placed=frame.createNode('python','place_T_joint');placed.setInput(0,local);placed.setInput(1,host)
  for name,value,label in [('bottom',-.12,'Lower end Y (m)'),('contact_gap',0.,'Visual gap / exploded view (m)'),('lateral_offset',0.,'Across section offset (m)')]:
   placed.addSpareParmTuple(hou.FloatParmTemplate(name,label,1,default_value=(value,)))
  code=PLACEMENT_CODE.replace('SIDE_VALUE',str(side))
  placed.parm('python').set(code)
  output=frame.createNode('null','OUT_PLACED_CHANNEL');output.setInput(0,placed);output.setDisplayFlag(True);output.setRenderFlag(True)
  output.cook(force=True);assert not output.errors(),output.errors()
  check=inspect(rackout.geometry(),output.geometry());assert check['passed'],check;checks[output.path()]=check
  frames.append(output.path())
  frame.setUserData('workai_candidate_status','User-corrected T end joint; fastening and upper host unknown')
  for name,delta in [('floating',(0,0,side*.006)),('penetrating',(0,0,-side*.003)),('off_axis',(.15,0,0))]:
   bad=hou.Geometry();bad.merge(output.geometry());bad.transform(hou.hmath.buildTranslate(delta));check=inspect(rackout.geometry(),bad)
   assert not check['passed'];negative[frame.name()+'/'+name]=check['issues']
  saved=detailed(output.geometry());placed.parm('bottom').set(-.18);output.cook(force=True)
  assert inspect(rackout.geometry(),output.geometry())['passed']
  placed.parm('bottom').set(-.12);output.cook(force=True);assert detailed(output.geometry())==saved
  frame.layoutChildren()
 after=detailed(rackout.geometry());diff=compare(before,after)
 assert set(diff['removed'])==set(RETIRED) and set(diff['changed'])=={STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1'} and not diff['added'] and len(diff['unchanged'])==215,diff
 assert original_material==parent.parm('shop_materialpath').eval() and parent.worldTransform()==hou.hmath.identityTransform()
 crossarm_check=verify_crossarm(rackout.geometry())
 pair_clearance=separation(*(bounds(hou.node(path).geometry()) for path in frames));assert pair_clearance>1
 parent.layoutChildren()
 report=dict(crossarm_check=crossarm_check,source_hashes=sources,inheritance=diff,checks=checks,counterexamples=negative,asset_path=asset.path(),rack_output=rackout.path(),frame_outputs=frames,
  library=str(delivery),library_sha=hashlib.sha256(delivery.read_bytes()).hexdigest(),rack_detail_sha=after,frame_detail_sha={p:detailed(hou.node(p).geometry()) for p in frames},
  source_channel_local_sha=local_shas,frame_pair_clearance=pair_clearance,slot_count_per_frame=17,total_visible_parts=220,
  scope='Foreground existing three-pipe tier, two inferred vertical channels, one end-trimmed crossarm with unchanged U-leg holes. Upper tiers not invented from sketch. No hidden fastening/anchors.')
 cam=hou.node('/obj/accept_camera');cam.parm('orthowidth').set(4.15);aim(cam,(0,.50,0),(5,3,-6))
 light=hou.node('/obj').createNode('hlight::2.0','frame_fill');light.parm('light_type').set(2);light.parmTuple('areasize').set((1,1.5));light.parm('light_intensity').set(1.2);aim(light,(.6,.35,-.85),(1,1,-2))
 front=hou.node('/obj').createNode('hlight::2.0','frame_front_softbox');front.parm('light_type').set(2);front.parmTuple('areasize').set((2.3,1.8));front.parm('light_intensity').set(1.0);aim(front,(.64,.35,0),(2,.1,0))
 hou.hipFile.save(str(out/'assembly.hip'))
 isolated=parent.createNode('python','isolate_host_station');isolated.setInput(0,rackout)
 isolated.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name") not in '+repr((STATION+'_web',STATION+'_lip_-1',STATION+'_lip_1'))+'])')
 isolated.setDisplayFlag(True);isolated.setRenderFlag(True)
 cam.parm('orthowidth').set(2.15);aim(cam,(.64,.39,-.02),(2,.25,-.30));hou.hipFile.save(str(out/'frame-only.hip'))
 cam.parm('orthowidth').set(.27);aim(cam,(.60,.030,-.865),(.7,.4,.8));hou.hipFile.save(str(out/'lap-detail.hip'))
 cam.parm('orthowidth').set(.27);aim(cam,(.60,.030,-.865),(-.7,.4,.8));hou.hipFile.save(str(out/'lap-reverse.hip'))
 rackout.setDisplayFlag(True);rackout.setRenderFlag(True)
 cam.parm('orthowidth').set(2.3);aim(cam,(.3,.50,0),(6,.06,0));hou.hipFile.save(str(out/'end.hip'))
 cam.parm('orthowidth').set(3.5);aim(cam,(0,.1,0),(0,6,.001));hou.hipFile.save(str(out/'top.hip'))
 hou.hipFile.load(str(out/'assembly.hip'),suppress_save_prompt=True)
 assert detailed(hou.node(report['rack_output']).geometry())==after
 for path in frames:
  g=hou.node(path).geometry();assert detailed(g)==report['frame_detail_sha'][path]
  assert inspect(hou.node(report['rack_output']).geometry(),g)['passed']
 for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
 report['saved_reopened']=True;report['passed']=True
 (out/'native-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(passed=True,checks=checks,counterexamples=negative,total_visible_parts=220)))


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--rack',required=True);parser.add_argument('--channel',required=True);parser.add_argument('--output',required=True)
 build(parser.parse_args())
