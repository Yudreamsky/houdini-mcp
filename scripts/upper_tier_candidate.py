"""One photo-guided upper crossarm and hollow duct; fixed saved T-frame baseline.

Run in hython. Dimensions and upper-tier assignment are visual estimates.
Embedded SOPs cook without this repository. Not a managed MCP recipe.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from paired_frame_candidate import detailed,bounds,aim,part
from houdini_mcp_local.assembly_checks import separation
from houdini_mcp_local.pad_checks import topology

FRAME_PATHS=('/obj/S1_channel_study/OUT_PLACED_CHANNEL','/obj/S1_other_side/OUT_PLACED_CHANNEL')
RACK='/obj/workai_ea67e5f3e0497f56/OUT_FRAME_CANDIDATE'
ARM='/obj/upper_crossarm/OUT_UPPER_CROSSARM'
DUCT='/obj/upper_duct/OUT_DUCT'
CONTROL='/obj/upper_duct/visual_parameters'

DUCT_CODE='''import hou,math,json
n=hou.pwd();g=n.geometry();g.clear()
L,W,H,t,y,z=(n.evalParm(k) for k in ('length','width','height','wall','tier_y','center_z'))
if not all(math.isfinite(v) for v in (L,W,H,t,y,z)):raise ValueError('Non-finite duct parameter')
if not (.5<=L<=3 and .15<=W<=.8 and .10<=H<=.30 and .0008<=t<=.003):raise ValueError('Outside visual study envelope')
if not .49<=y<=.60 or abs(z)+W/2>.75:raise ValueError('Outside frozen rack clearance envelope')
if min(W,H)<4*t:raise ValueError('Invalid wall thickness')
outer=[(0,0),(H,0),(H,W),(0,W)]
inner=[(t,t),(H-t,t),(H-t,W-t),(t,W-t)]
points=[]
for x in (-L/2,L/2):
 for ring in (outer,inner):
  for yy,zz in ring:
   p=g.createPoint();p.setPosition((x,y+yy,z-W/2+zz));points.append(p)
faces=[]
for i in range(4):
 j=(i+1)%4
 faces += [[i,j,8+j,8+i],[4+j,4+i,12+i,12+j],
           [j,i,4+i,4+j],[8+i,8+j,12+j,12+i]]
# Signed volume determines consistent outward winding for the closed sheet shell.
volume=0
for face in faces:
 a=points[face[0]].position()
 for i in range(1,len(face)-1):volume+=a.dot(points[face[i]].position().cross(points[face[i+1]].position()))/6
if volume<0:faces=[list(reversed(f)) for f in faces]
g.addAttrib(hou.attribType.Prim,'name','upper_duct_shell')
g.addAttrib(hou.attribType.Prim,'part_type','rectangular_duct')
g.addAttrib(hou.attribType.Prim,'Cd',(0.48,0.52,0.56))
g.addAttrib(hou.attribType.Prim,'shop_materialpath','/mat/duct_galvanized')
for face in faces:
 p=g.createPolygon()
 p.setAttribValue('name','upper_duct_shell');p.setAttribValue('part_type','rectangular_duct')
 p.setAttribValue('Cd',(.48,.52,.56));p.setAttribValue('shop_materialpath','/mat/duct_galvanized')
 for i in face:p.addVertex(points[i])
g.addAttrib(hou.attribType.Global,'duct_spec','')
g.setGlobalAttribValue('duct_spec',json.dumps(dict(length=L,width=W,height=H,wall=t,bottom=y,center_z=z,source='photo-guided estimates',ends='open segment boundaries',hidden_fastening='unmodeled')))
'''

PLACE_ARM='''import hou,json
n=hou.pwd();g=n.geometry();g.clear();g.merge(n.inputs()[0].geometry())
left=n.inputs()[1].geometry().boundingBox().maxvec()[2]
right=n.inputs()[2].geometry().boundingBox().minvec()[2]
L=g.boundingBox().sizevec()[2]
if abs(L-(right-left))>3e-6:raise ValueError('Upper crossarm span does not match saved uprights')
top=hou.node('/obj/upper_duct/visual_parameters').evalParm('tier_y')
g.transform(hou.hmath.buildTranslate((.6,top-g.boundingBox().maxvec()[1],(left+right)/2)))
for p in g.prims():p.setAttribValue('name','upper_crossarm');p.setAttribValue('part_type','slotted_crossarm')
'''

def closed(node):
 node.cook(force=True);assert not node.errors(),node.errors();g=node.geometry()
 t=topology(dict(points=[list(p.position()) for p in g.points()],faces=[[v.point().number() for v in p.vertices()] for p in g.prims()]))
 assert t['closed'] and t['components']==1 and t['signed_volume']>0,t
 return t

def ray(g,origin,direction,limit):
 hit=hou.Vector3()
 index=g.intersect(hou.Vector3(origin),hou.Vector3(direction),hit,hou.Vector3(),hou.Vector3(),min_hit=1e-7,max_hit=limit,tolerance=1e-7)
 return index,list(hit)

def joints(arm,frames):
 ab=bounds(arm);results=[]
 for frame,side in zip(frames,(-1,1)):
  fb=bounds(frame);plane=fb[1 if side<0 else 0][2];end=ab[0 if side<0 else 1][2]
  hits=0
  for i in range(13):
   x=ab[0][0]+(ab[1][0]-ab[0][0])*(i+.5)/13
   for frac in (.02,.04,.08,.25,.50,.93,.97):
    y=ab[0][1]+(ab[1][1]-ab[0][1])*frac
    ia,a=ray(arm,(x,y,plane+side*.001),(0,0,-side),.004)
    ib,b=ray(frame,(x,y,plane-side*.001),(0,0,side),.004)
    if ia>=0 and ib>=0 and abs(a[2]-plane)<3e-6 and abs(b[2]-plane)<3e-6:hits+=1
  results.append(dict(side=side,end_gap=end-plane,samples=hits,total=91,passed=abs(end-plane)<3e-6 and hits>=6))
 return dict(passed=all(r['passed'] for r in results),ends=results)

def support(arm,duct):
 ab=bounds(arm);db=bounds(duct);gap=db[0][1]-ab[1][1];hits=0
 for dx in (-.018,-.014,.014,.018):
  for f in (.15,.30,.50,.70,.85):
   x=.6+dx;z=db[0][2]+(db[1][2]-db[0][2])*f
   ia,a=ray(arm,(x,ab[1][1]+.001,z),(0,-1,0),.004)
   ib,b=ray(duct,(x,db[0][1]-.001,z),(0,1,0),.004)
   if ia>=0 and ib>=0 and abs(a[1]-b[1])<3e-6:hits+=1
 return dict(passed=abs(gap)<3e-6 and hits>=12,gap=gap,contact_samples=hits,total=20)

def passage(duct):
 db=bounds(duct);yc=(db[0][1]+db[1][1])/2;zc=(db[0][2]+db[1][2])/2;length=db[1][0]-db[0][0];results=[]
 for fy in (.15,.50,.85):
  for fz in (.15,.50,.85):
   y=db[0][1]+(db[1][1]-db[0][1])*fy;z=db[0][2]+(db[1][2]-db[0][2])*fz
   results.append(ray(duct,(db[0][0]-.01,y,z),(1,0,0),length+.02)[0]==-1)
 walls=[]
 for direction in ((0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
  walls.append(ray(duct,(0,yc,zc),direction,1)[0]>=0)
 return dict(passed=all(results+walls),clear_axial_rays=sum(results),walls_present=sum(walls))

def inherited():
 return {p:dict(parts=detailed(hou.node(p).geometry()),matrix=list(hou.node(p).parent().worldTransform().asTuple()),material=hou.node(p).parent().parm('shop_materialpath').eval()) for p in (RACK,)+FRAME_PATHS}

def build(args):
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
 source=Path(args.source).resolve();source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
 hou.hipFile.load(str(source),suppress_save_prompt=True);before=inherited()
 asset=next(n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')=='pipe_rack_all_pads')
 asset_path=asset.path()
 library=Path(asset.type().definition().libraryFilePath());libsha=hashlib.sha256(library.read_bytes()).hexdigest()
 delivery=out/library.name;shutil.copy2(library,delivery);hou.hda.installFile(str(delivery))
 for definition in hou.hda.definitionsInFile(str(delivery)):definition.setIsPreferred(True)
 assert asset.matchesCurrentDefinition()
 obj=hou.node('/obj').createNode('geo','upper_duct')
 for node in obj.children():node.destroy()
 parameters=obj.createNode('python','visual_parameters')
 for name,value in dict(length=2.8,width=.55,height=.24,wall=.0012,tier_y=.55,center_z=.10).items():
  parameters.addSpareParmTuple(hou.FloatParmTemplate(name,name.replace('_',' ').title()+' (m, estimated)',1,default_value=(value,)))
 parameters.parm('python').set(DUCT_CODE)
 bevel=obj.createNode('polybevel::3.0','small_manufactured_edges');bevel.setInput(0,parameters)
 bevel.parm('offset').set(.00025);bevel.parm('divisions').set(2);bevel.parm('filletshape').set(4)
 normals=obj.createNode('normal','planar_normals');normals.setInput(0,bevel);normals.parm('type').set(1);normals.parm('cuspangle').set(20)
 duct=obj.createNode('null','OUT_DUCT');duct.setInput(0,normals);duct.setDisplayFlag(True);duct.setRenderFlag(True)
 mat=hou.node('/mat').createNode('principledshader::2.0','duct_galvanized');mat.parm('basecolor_usePointColor').set(0)
 mat.parmTuple('basecolor').set((.5,.54,.58));mat.parm('metallic').set(.75);mat.parm('rough').set(.36);obj.parm('shop_materialpath').set(mat.path())
 frame_geos=[hou.node(p).geometry() for p in FRAME_PATHS];span=bounds(frame_geos[1])[0][2]-bounds(frame_geos[0])[1][2]
 cross=hou.copyNodesTo((hou.node('/obj/S1_channel_study'),),hou.node('/obj'))[0];cross.setName('upper_crossarm',unique_name=False)
 for name in ('OUT_PLACED_CHANNEL','place_T_joint','actual_rack_host'):cross.node(name).destroy()
 cross.node('channel_parameters').parm('length').set(span)
 hosts=[]
 for i,path in enumerate(FRAME_PATHS):
  node=cross.createNode('object_merge','upright_'+str(i));node.parm('objpath1').set(path);node.parm('xformtype').set(1);hosts.append(node)
 placement=cross.createNode('python','place_between_uprights');placement.setInput(0,cross.node('OUT_CHANNEL'))
 for i,node in enumerate(hosts,1):placement.setInput(i,node)
 placement.parm('python').set(PLACE_ARM)
 arm=cross.createNode('null','OUT_UPPER_CROSSARM');arm.setInput(0,placement);arm.setDisplayFlag(True);arm.setRenderFlag(True)
 armtop=closed(arm);ducttop=closed(duct);rawtop=closed(parameters)
 p={n:parameters.evalParm(n) for n in ('length','width','height','wall','tier_y','center_z')}
 volume=p['length']*(p['width']*p['height']-(p['width']-2*p['wall'])*(p['height']-2*p['wall']))
 assert abs(rawtop['signed_volume']-volume)<volume*1e-4
 assert ducttop['euler']==0
 spec=json.loads(arm.geometry().attribValue('channel_spec'));slots=len(spec['slot_centers'])
 assert armtop['euler']==2-2*slots
 ab=bounds(arm.geometry());zc=(ab[0][2]+ab[1][2])/2
 for z in spec['slot_centers']:assert ray(arm.geometry(),(.6,ab[1][1]+.01,zc+z),(0,-1,0),.06)[0]==-1
 connection=joints(arm.geometry(),frame_geos);bearing=support(arm.geometry(),duct.geometry());flow=passage(duct.geometry())
 assert connection['passed'],connection
 assert bearing['passed'],bearing
 assert flow['passed'],flow
 # Full old geometry is preserved; prove separation from old rack and the two upright envelopes.
 rackbox=bounds(hou.node(RACK).geometry())
 # The rear old hangers rise above the new tier but lie at a different X. Check by part, not total bbox.
 old_geo=hou.node(RACK).geometry();boxes={}
 for prim in old_geo.prims():
  box=boxes.setdefault(prim.attribValue('name'),[[float('inf')]*3,[-float('inf')]*3])
  for v in prim.vertices():
   for i,value in enumerate(v.point().position()):box[0][i]=min(box[0][i],value);box[1][i]=max(box[1][i],value)
 clear={}
 for label,g in (('arm',arm.geometry()),('duct',duct.geometry())):
  nearest=min((separation(bounds(g),b),name) for name,b in boxes.items());assert nearest[0]>.001,nearest
  clear[label]=dict(aabb_clearance_lower_bound=nearest[0],part=nearest[1])
 for i,g in enumerate(frame_geos):assert separation(bounds(duct.geometry()),bounds(g))>.001
 negative={}
 for label,delta in [('arm_short_end', (0,0,.006)),('arm_cross_axis',(.15,0,0))]:
  bad=hou.Geometry();bad.merge(arm.geometry());bad.transform(hou.hmath.buildTranslate(delta));negative[label]=not joints(bad,frame_geos)['passed']
 for label,dy in [('duct_floating',.006),('duct_penetrating',-.003)]:
  bad=hou.Geometry();bad.merge(duct.geometry());bad.transform(hou.hmath.buildTranslate((0,dy,0)));negative[label]=not support(arm.geometry(),bad)['passed']
 bad=hou.Geometry();bad.merge(duct.geometry());db=bounds(bad);poly=bad.createPolygon()
 for y,z in ((db[0][1],db[0][2]),(db[1][1],db[0][2]),(db[1][1],db[1][2]),(db[0][1],db[1][2])):
  pt=bad.createPoint();pt.setPosition((0,y,z));poly.addVertex(pt)
 negative['blocked_duct']=not passage(bad)['passed'];assert all(negative.values()),negative
 original={path:detailed(hou.node(path).geometry()) for path in (ARM,DUCT)}
 parameters.parm('tier_y').set(.58);parameters.parm('width').set(.65)
 assert joints(arm.geometry(),frame_geos)['passed'] and support(arm.geometry(),duct.geometry())['passed'] and passage(duct.geometry())['passed']
 parameters.parm('tier_y').set(.55);parameters.parm('width').set(.55)
 assert original=={path:detailed(hou.node(path).geometry()) for path in (ARM,DUCT)}
 assert before==inherited()
 obj.layoutChildren();cross.layoutChildren()
 cam=hou.node('/obj/accept_camera');cam.parm('orthowidth').set(4.15);aim(cam,(0,.50,0),(5,3,-6))
 hou.hipFile.save(str(out/'assembly.hip'))
 # Full front elevation includes the rear rack to preserve scene context.
 cam.parm('orthowidth').set(2.3);aim(cam,(.3,.48,0),(6,.05,0));hou.hipFile.save(str(out/'end.hip'))
 cam.parm('orthowidth').set(3.5);aim(cam,(0,.40,0),(0,6,.001));hou.hipFile.save(str(out/'top.hip'))
 # Isolated frame + upper duct, keeping only the foreground lower crossarm in the rack.
 rack=hou.node(RACK);isolated=rack.parent().createNode('python','isolate_host_station_upper_review');isolated.setInput(0,rack)
 isolated.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name") not in ("rack_pos_0_web","rack_pos_0_lip_-1","rack_pos_0_lip_1")])')
 isolated.setDisplayFlag(True);isolated.setRenderFlag(True)
 cam.parm('orthowidth').set(2.15);aim(cam,(.6,.42,-.02),(3,.45,-.35));hou.hipFile.save(str(out/'tier-only.hip'))
 # Close end view makes the hollow duct and its supporting web visible.
 cam.parm('orthowidth').set(1.12);aim(cam,(.85,.65,.10),(3,1.2,-1.1));hou.hipFile.save(str(out/'duct-detail.hip'))
 # Rear view of both T connections with the duct hidden for coverage verification.
 obj.setDisplayFlag(False);cam.parm('orthowidth').set(2.10);aim(cam,(.6,.43,-.02),(-3,.55,.25));hou.hipFile.save(str(out/'frame-reverse.hip'))
 hou.hipFile.load(str(out/'assembly.hip'),suppress_save_prompt=True)
 assert before==inherited() and original=={path:detailed(hou.node(path).geometry()) for path in (ARM,DUCT)}
 assert source_sha==hashlib.sha256(source.read_bytes()).hexdigest()
 report=dict(passed=True,source=str(source),source_sha256=source_sha,source_library=str(library),source_library_sha256=libsha,library=str(delivery),asset_path=asset_path,
  retained=before,retained_part_count=sum(len(v['parts']) for v in before.values()),new_fingerprints=original,new_part_count=2,total_parts=222,
  parameters=p,crossarm_slots=slots,arm_topology=armtop,duct_topology=ducttop,analytic_shell_volume=volume,raw_shell_volume=rawtop['signed_volume'],
  joints=connection,support=bearing,passage=flow,clearances=clear,counterexamples=negative,parameter_change_reset=True,saved_reopened=True,
  scope='One estimated upper tier and one continuous hollow duct segment; other upper utilities, duct joints, concealed fastening, longitudinal supports and exact photo camera remain unmodeled')
 (out/'native-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({k:report[k] for k in ('passed','total_parts','crossarm_slots','joints','support','passage','counterexamples')}),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
 build(parser.parse_args())
