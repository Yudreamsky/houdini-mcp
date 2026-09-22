"""Split the saved visual duct into two hollow segments with an external seam.

Dimensions and joint type are photo-guided estimates, not fabrication details.
No hidden fasteners, gasket or seal performance is claimed. Run with hython.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from paired_frame_candidate import detailed,bounds,aim,part
from upper_tier_candidate import inherited,ARM,DUCT,CONTROL,FRAME_PATHS,RACK,ray,passage,joints
from houdini_mcp_local.pad_checks import topology
from houdini_mcp_local.assembly_checks import separation

SEAM_CODE='''import hou,json,math
n=hou.pwd();g=n.geometry();g.clear()
p=json.loads(n.inputs()[0].geometry().attribValue('duct_spec'))
L,W,H,t,y,z=(p[k] for k in ('length','width','height','wall','bottom','center_z'))
c,e,f,gap=(n.evalParm(k) for k in ('seam_x','flange_projection','flange_thickness','seam_gap'))
if not all(math.isfinite(v) for v in (c,e,f,gap)):raise ValueError('Non-finite seam parameter')
if not (.006<=e<=.025 and .002<=f<=.006 and .001<=gap<=.004):raise ValueError('Outside estimated seam envelope')
if abs(c)+gap/2+f>L/2-.15:raise ValueError('Seam too close to a segment boundary')
arm=hou.node('/obj/upper_crossarm/OUT_UPPER_CROSSARM').geometry().boundingBox()
if c+gap/2+f>=arm.minvec()[0]-.03 and c-gap/2-f<=arm.maxvec()[0]+.03:raise ValueError('Seam overlaps upper crossarm support band')
g.addAttrib(hou.attribType.Prim,'name','')
g.addAttrib(hou.attribType.Prim,'part_type','rectangular_duct_segment')
g.addAttrib(hou.attribType.Prim,'Cd',(.48,.52,.56))
g.addAttrib(hou.attribType.Prim,'shop_materialpath','/mat/duct_galvanized')
segments=[('upper_duct_left',[(-L/2,0),(c-gap/2-f,0),(c-gap/2-f,e),(c-gap/2,e)]),
          ('upper_duct_right',[(c+gap/2,e),(c+gap/2+f,e),(c+gap/2+f,0),(L/2,0)])]
for name,stations in segments:
 points=[];faces=[]
 for x,ext in stations:
  for yy,zz in [(-ext,-ext),(H+ext,-ext),(H+ext,W+ext),(-ext,W+ext)]:
   q=g.createPoint();q.setPosition((x,y+yy,z-W/2+zz));points.append(q)
 for x in (stations[0][0],stations[-1][0]):
  for yy,zz in [(t,t),(H-t,t),(H-t,W-t),(t,W-t)]:
   q=g.createPoint();q.setPosition((x,y+yy,z-W/2+zz));points.append(q)
 for i in range(4):
  j=(i+1)%4
  for k in range(3):faces.append([4*k+i,4*k+j,4*(k+1)+j,4*(k+1)+i])
  faces += [[16+j,16+i,20+i,20+j],[j,i,16+i,16+j],[12+i,12+j,20+j,20+i]]
 volume=0
 for face in faces:
  a=points[face[0]].position()
  for i in range(1,len(face)-1):volume+=a.dot(points[face[i]].position().cross(points[face[i+1]].position()))/6
 if volume<0:faces=[list(reversed(face)) for face in faces]
 for face in faces:
  prim=g.createPolygon();prim.setAttribValue('name',name)
  prim.setAttribValue('part_type','rectangular_duct_segment');prim.setAttribValue('Cd',(.48,.52,.56));prim.setAttribValue('shop_materialpath','/mat/duct_galvanized')
  for i in face:prim.addVertex(points[i])
p.update(seam_x=c,flange_projection=e,flange_thickness=f,seam_gap=gap,hidden_seal='unmodeled',hidden_fasteners='unmodeled')
g.addAttrib(hou.attribType.Global,'duct_spec','');g.setGlobalAttribValue('duct_spec',json.dumps(p))
'''

def fixed():
 data=inherited();node=hou.node(ARM)
 data[ARM]=dict(parts=detailed(node.geometry()),matrix=list(node.parent().worldTransform().asTuple()),material=node.parent().parm('shop_materialpath').eval())
 return data

def topo(g):
 return topology(dict(points=[list(p.position()) for p in g.points()],faces=[[v.point().number() for v in f.vertices()] for f in g.prims()]))

def seam_check(g):
 spec=json.loads(g.attribValue('duct_spec'));left=part(g,'upper_duct_left');right=part(g,'upper_duct_right');lb=bounds(left);rb=bounds(right)
 gap=rb[0][0]-lb[1][0];hits=[];c=spec['seam_x'];y=spec['bottom'];z=spec['center_z'];W=spec['width'];H=spec['height'];e=spec['flange_projection'];f=spec['flange_thickness']
 sites=[(y+H+e*.5,z),(y-e*.5,z),(y+H*.5,z-W/2-e*.5),(y+H*.5,z+W/2+e*.5)]
 for yy,zz in sites:
  il,a=ray(left,(c,yy,zz),(-1,0,0),.03);ir,b=ray(right,(c,yy,zz),(1,0,0),.03)
  hits.append(il>=0 and ir>=0 and abs(a[0]-lb[1][0])<3e-6 and abs(b[0]-rb[0][0])<3e-6)
 # No external flange may be floating away from its own duct sheet.
 tops=[topo(left),topo(right)]
 wellformed=all(t['closed'] and t['components']==1 and t['euler']==0 and t['minimum_face_area']>0 and t['signed_volume']>0 for t in tops)
 alignment=max(abs(lb[i][a]-rb[i][a]) for i in (0,1) for a in (1,2))
 return dict(passed=wellformed and all(hits) and abs(gap-spec['seam_gap'])<3e-6 and alignment<3e-6,gap=gap,aligned_yz_error=alignment,flange_sides_verified=sum(hits),topology=tops)

def bearing(arm,g):
 ab=bounds(arm);spec=json.loads(g.attribValue('duct_spec'));y=ab[1][1];hits=0
 for dx in (-.018,-.014,.014,.018):
  for f in (.15,.30,.50,.70,.85):
   x=.6+dx;z=spec['center_z']+spec['width']*(f-.5)
   ia,a=ray(arm,(x,y+.001,z),(0,-1,0),.004);ib,b=ray(g,(x,y-.001,z),(0,1,0),.004)
   if ia>=0 and ib>=0 and abs(a[1]-b[1])<3e-6:hits+=1
 coverage=[]
 for name in ('upper_duct_left','upper_duct_right'):
  b=bounds(part(g,name))
  if b[0][0]<ab[0][0]-.001 and b[1][0]>ab[1][0]+.001:coverage.append(name)
 # A seam ring is below the duct underside elsewhere; global minY is not its support plane.
 return dict(passed=hits==20 and coverage==['upper_duct_right'],samples=hits,total=20,full_support_band_in=coverage)

def build(args):
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);source=Path(args.source).resolve();sha=hashlib.sha256(source.read_bytes()).hexdigest()
 hou.hipFile.load(str(source),suppress_save_prompt=True);before=fixed();assert sum(len(v['parts']) for v in before.values())==221
 old=detailed(hou.node(DUCT).geometry());assert set(old) in ({''},{'upper_duct_shell'}),'Unexpected duct components in frozen source'
 asset=next(n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')=='pipe_rack_all_pads');asset_path=asset.path()
 library=Path(asset.type().definition().libraryFilePath());libsha=hashlib.sha256(library.read_bytes()).hexdigest();delivery=out/library.name;shutil.copy2(library,delivery)
 hou.hda.installFile(str(delivery))
 for definition in hou.hda.definitionsInFile(str(delivery)):definition.setIsPreferred(True)
 assert asset.matchesCurrentDefinition()
 obj=hou.node('/obj/upper_duct');split=obj.createNode('python','section_joint');split.setInput(0,hou.node(CONTROL))
 for name,value in dict(seam_x=-.15,flange_projection=.012,flange_thickness=.003,seam_gap=.002).items():
  split.addSpareParmTuple(hou.FloatParmTemplate(name,name.replace('_',' ').title()+' (m, estimated)',1,default_value=(value,)))
 split.parm('python').set(SEAM_CODE)
 bevel=obj.createNode('polybevel::3.0','joint_edge_roundovers');bevel.setInput(0,split);bevel.parm('offset').set(.00025);bevel.parm('divisions').set(2);bevel.parm('filletshape').set(4)
 normal=obj.createNode('normal','joint_normals');normal.setInput(0,bevel);normal.parm('type').set(1);normal.parm('cuspangle').set(20)
 duct=hou.node(DUCT);duct.setInput(0,normal);duct.cook(force=True);assert not duct.errors(),duct.errors()
 assert set(detailed(duct.geometry()))=={'upper_duct_left','upper_duct_right'}
 assert all(p.attribValue('part_type')=='rectangular_duct_segment' and p.attribValue('shop_materialpath')=='/mat/duct_galvanized' for p in duct.geometry().prims())
 check=seam_check(duct.geometry());assert check['passed'],check
 flow=passage(duct.geometry());assert flow['passed'],flow
 seat=bearing(hou.node(ARM).geometry(),duct.geometry());assert seat['passed'],seat
 spec=json.loads(duct.geometry().attribValue('duct_spec'));L=spec['length'];W=spec['width'];H=spec['height'];t=spec['wall'];gap=spec['seam_gap'];e=spec['flange_projection'];f=spec['flange_thickness']
 analytic=(L-gap)*(W*H-(W-2*t)*(H-2*t))+2*f*((W+2*e)*(H+2*e)-W*H)
 raw=topo(split.geometry());assert abs(raw['signed_volume']-analytic)<analytic*2e-5,(raw,analytic)
 # Adjacent lower assets are unchanged; check each part against the changed duct bounds.
 boxes={}
 for path in (RACK,)+FRAME_PATHS:
  for prim in hou.node(path).geometry().prims():
   box=boxes.setdefault(prim.attribValue('name'),[[float('inf')]*3,[-float('inf')]*3])
   for v in prim.vertices():
    for i,value in enumerate(v.point().position()):box[0][i]=min(box[0][i],value);box[1][i]=max(box[1][i],value)
 nearest=min((separation(bounds(duct.geometry()),b),name) for name,b in boxes.items());assert nearest[0]>.001,nearest
 arm_box=bounds(hou.node(ARM).geometry());seam_span=(spec['seam_x']-gap/2-f,spec['seam_x']+gap/2+f)
 assert seam_span[1]<arm_box[0][0]-.03
 negative={}
 for label,delta in [('seam_overlap',(-.004,0,0)),('seam_open',(.006,0,0)),('segment_misaligned',(0,.006,0))]:
  bad=hou.Geometry();bad.merge(duct.geometry());ids={v.point().number() for p in bad.prims() if p.attribValue('name')=='upper_duct_right' for v in p.vertices()}
  for point in bad.points():
   if point.number() in ids:point.setPosition(point.position()+hou.Vector3(delta))
  negative[label]=not seam_check(bad)['passed']
 bad=hou.Geometry();bad.merge(duct.geometry());bad.transform(hou.hmath.buildTranslate((0,.006,0)));negative['floating_duct']=not bearing(hou.node(ARM).geometry(),bad)['passed']
 bad=hou.Geometry();bad.merge(duct.geometry());poly=bad.createPolygon()
 for yy,zz in ((spec['bottom'],spec['center_z']-W/2),(spec['bottom']+H,spec['center_z']-W/2),(spec['bottom']+H,spec['center_z']+W/2),(spec['bottom'],spec['center_z']+W/2)):
  p=bad.createPoint();p.setPosition((-.4,yy,zz));poly.addVertex(p)
 negative['blocked_duct']=not passage(bad)['passed'];assert all(negative.values()),negative
 reset=detailed(duct.geometry());split.parm('seam_x').set(-.35)
 assert seam_check(duct.geometry())['passed'] and bearing(hou.node(ARM).geometry(),duct.geometry())['passed']
 split.parm('seam_x').set(.6)
 try:split.cook(force=True)
 except hou.OperationFailed:pass
 assert split.errors(),'Seam over support not rejected'
 split.parm('seam_x').set(-.15);duct.cook(force=True);assert detailed(duct.geometry())==reset
 assert fixed()==before;obj.layoutChildren()
 cam=hou.node('/obj/accept_camera');cam.parm('orthowidth').set(4.15);aim(cam,(0,.50,0),(5,3,-6));hou.hipFile.save(str(out/'assembly.hip'))
 # Local exterior and opposite lower face include the seam around all four sides.
 for node in hou.node('/obj').children():
  if node.type().name()=='geo' and node!=obj:node.setDisplayFlag(False)
 cam.parm('orthowidth').set(.95);aim(cam,(-.15,.67,.10),(2,1.7,-2));hou.hipFile.save(str(out/'seam-detail.hip'))
 review=hou.node('/obj').createNode('hlight::2.0','seam_under_review_fill');review.parm('light_type').set(2);review.parmTuple('areasize').set((2,2));review.parm('light_intensity').set(.65);aim(review,(-.15,.55,.10),(2,-1.2,-2))
 cam.parm('orthowidth').set(.95);aim(cam,(-.15,.67,.10),(-2,-1.2,2));hou.hipFile.save(str(out/'seam-under.hip'));review.destroy()
 cam.parm('orthowidth').set(.95);aim(cam,(-.15,.67,.10),(3,.03,.03));hou.hipFile.save(str(out/'duct-end.hip'))
 # Whole isolated duct for longitudinal coverage; inherited lower geometry needs no rerender.
 cam.parm('orthowidth').set(3.4);aim(cam,(0,.67,.10),(2,1.5,-4));hou.hipFile.save(str(out/'duct-only.hip'))
 hou.hipFile.load(str(out/'assembly.hip'),suppress_save_prompt=True)
 assert fixed()==before and detailed(hou.node(DUCT).geometry())==reset
 assert sha==hashlib.sha256(source.read_bytes()).hexdigest() and libsha==hashlib.sha256(library.read_bytes()).hexdigest()
 report=dict(passed=True,source=str(source),source_sha256=sha,source_library=str(library),source_library_sha256=libsha,library=str(delivery),asset_path=asset_path,
 retained=before,retained_count=221,retired_source_parts=old,retired_source_path=DUCT,source_identity_missing=set(old)=={''},new_fingerprints={DUCT:reset},total_parts=223,seam=check,passage=flow,bearing=seat,parameters=spec,
 analytic_volume=analytic,raw_volume=raw['signed_volume'],nearest_old_part=dict(name=nearest[1],aabb_clearance_lower_bound=nearest[0]),counterexamples=negative,
 seam_move_reset=True,seam_over_support_rejected=True,saved_reopened=True,scope='Visible external joint candidate only; hidden bolts/seal and longitudinal support remain unmodeled')
 (out/'native-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('passed','retained_count','total_parts','seam','bearing','counterexamples')}),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);build(parser.parse_args())
