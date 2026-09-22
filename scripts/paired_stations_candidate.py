"""Replace the frozen rear placeholders with a second two-tier T-frame.

Photo-guided visual layout; existing station spacing is an estimate, not a
measured support design. No anchors, hidden fastening or load capacity claim.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import paired_frame_candidate as framecheck
from paired_frame_candidate import detailed,bounds,part,aim
from upper_tier_candidate import RACK,ARM,DUCT,CONTROL,FRAME_PATHS,joints,ray
from duct_seam_candidate import seam_check,passage
from houdini_mcp_local.assembly_checks import compare,separation
from houdini_mcp_local.pad_checks import topology

STATION='rack_neg_0'
BEAMS=tuple(STATION+s for s in ('_web','_lip_-1','_lip_1'))
RETIRED=tuple(STATION+s for side in (-1,1) for s in (f'_rod_{side}',f'_anchor_{side}',f'_nut_{side}_0.031',f'_nut_{side}_0.044'))
BASE=(RACK,)+FRAME_PATHS+(ARM,DUCT)

def record(paths):
 return {path:dict(parts=detailed(hou.node(path).geometry()),matrix=list(hou.node(path).parent().worldTransform().asTuple()),material=hou.node(path).parent().parm('shop_materialpath').eval()) for path in paths}

def allparts(records):
 result={}
 for r in records.values():
  assert not set(result)&set(r['parts']),'Duplicate visible component identity'
  result.update(r['parts'])
 return result

def topo(g):
 t=topology(dict(points=[list(p.position()) for p in g.points()],faces=[[v.point().number() for v in f.vertices()] for f in g.prims()]))
 assert t['closed'] and t['components']==1 and t['signed_volume']>0 and t['minimum_face_area']>0,t
 return t

def bearing(arms,duct):
 spec=json.loads(duct.attribValue('duct_spec'));segments={n:bounds(part(duct,n)) for n in ('upper_duct_left','upper_duct_right')};rows=[]
 for arm in arms:
  ab=bounds(arm);x=(ab[0][0]+ab[1][0])/2;y=ab[1][1];hits=0
  for dx in (-.018,-.014,.014,.018):
   for f in (.15,.30,.50,.70,.85):
    z=spec['center_z']+spec['width']*(f-.5)
    ia,a=ray(arm,(x+dx,y+.001,z),(0,-1,0),.004);ib,b=ray(duct,(x+dx,y-.001,z),(0,1,0),.004)
    if ia>=0 and ib>=0 and abs(a[1]-b[1])<3e-6:hits+=1
  cover=[name for name,b in segments.items() if b[0][0]<ab[0][0]-.001 and b[1][0]>ab[1][0]+.001]
  seam=(spec['seam_x']-spec['seam_gap']/2-spec['flange_thickness'],spec['seam_x']+spec['seam_gap']/2+spec['flange_thickness'])
  seam_clear=max(seam[0]-ab[1][0],ab[0][0]-seam[1])
  rows.append(dict(x=x,contact_samples=hits,cover=cover,seam_clearance=seam_clear,passed=hits==20 and len(cover)==1 and seam_clear>.03))
 covered=[name for r in rows for name in r['cover']]
 return dict(passed=len(rows)==2 and all(r['passed'] for r in rows) and sorted(covered)==sorted(segments),stations=rows)

def build(args):
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);source=Path(args.source).resolve();sha=hashlib.sha256(source.read_bytes()).hexdigest()
 hou.hipFile.load(str(source),suppress_save_prompt=True);before=record(BASE);before_parts=allparts(before);assert len(before_parts)==223
 asset=next(n for n in hou.node('/obj').allSubChildren() if n.userData('workai_recipe')=='pipe_rack_all_pads');asset_path=asset.path()
 library=Path(asset.type().definition().libraryFilePath());libsha=hashlib.sha256(library.read_bytes()).hexdigest();delivery=out/library.name;shutil.copy2(library,delivery)
 hou.hda.installFile(str(delivery))
 for definition in hou.hda.definitionsInFile(str(delivery)):definition.setIsPreferred(True)
 assert asset.matchesCurrentDefinition()
 rack=hou.node(RACK);parent=rack.parent();old=rack.inputs()[0];rod=part(old.geometry(),STATION+'_rod_-1');rb=bounds(rod);rear_x=(rb[0][0]+rb[1][0])/2
 retained=parent.createNode('python','retire_rear_hanger_placeholders');retained.setInput(0,old)
 retained.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name") in '+repr(RETIRED+BEAMS)+'])')
 merge=parent.createNode('merge','paired_station_rack');merge.setInput(0,retained)
 for k,name in enumerate(BEAMS,1):
  selected=parent.createNode('python','rear_crossarm_'+str(k));selected.setInput(0,old)
  selected.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name")!='+repr(name)+'])')
  previous=selected
  for side in (-1,1):
   b=bounds(part(old.geometry(),STATION+f'_rod_{side}'));z=(b[0][2]+b[1][2])/2-side*.020
   clip=parent.createNode('clip','rear_cut_'+str(k)+('_left' if side<0 else '_right'));clip.setInput(0,previous);clip.parmTuple('dir').set((0,0,-side));clip.parm('dist').set(-side*z);clip.parm('dofill').set(1);clip.parm('snaptol').set(1e-7);clip.parm('fillpolygons').set('new_end_caps');previous=clip
  caps=parent.createNode('normal','rear_end_normals_'+str(k));caps.setInput(0,previous);caps.parm('group').set('new_end_caps');caps.parm('grouptype').set(4);caps.parm('type').set(1);caps.parm('cuspangle').set(0)
  prim=next(p for p in selected.geometry().prims());values={a:prim.attribValue(a) for a in ('name','part_type','Cd','shop_materialpath')}
  tags=parent.createNode('python','rear_identity_'+str(k));tags.setInput(0,caps);tags.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\nvalues='+repr(values)+'\nfor p in g.prims():\n for key,value in values.items():p.setAttribValue(key,value)')
  merge.setInput(k,tags)
 rack.setInput(0,merge);rack.setDisplayFlag(True);rack.setRenderFlag(True)
 frames=[]
 for i,path in enumerate(FRAME_PATHS):
  obj=hou.copyNodesTo((hou.node(path).parent(),),hou.node('/obj'))[0];obj.setName('rear_upright_'+str(i),unique_name=False)
  node=obj.node('place_T_joint');code=node.parm('python').unexpandedString().replace('rack_pos_0_rod_','rack_neg_0_rod_').replace("'frame_redside'","'rear_frame_redside'").replace("'frame_blackside'","'rear_frame_blackside'")
  node.parm('python').set(code);frames.append(obj.node('OUT_PLACED_CHANNEL').path());obj.layoutChildren()
 upper=hou.copyNodesTo((hou.node(ARM).parent(),),hou.node('/obj'))[0];upper.setName('rear_upper_crossarm',unique_name=False)
 for i,path in enumerate(frames):upper.node('upright_'+str(i)).parm('objpath1').set(path)
 placement=upper.node('place_between_uprights');code=placement.parm('python').unexpandedString();assert '(.6,' in code
 code=code.replace('(.6,','('+repr(rear_x)+',').replace("'upper_crossarm'","'rear_upper_crossarm'");placement.parm('python').set(code)
 rear_arm=upper.node('OUT_UPPER_CROSSARM');upper.layoutChildren();new_paths=tuple(frames)+(rear_arm.path(),)
 # Add the second actual support to the seam guard; generated duct geometry stays identical.
 seam=hou.node('/obj/upper_duct/section_joint');code=seam.parm('python').unexpandedString()
 old_guard="arm=hou.node('/obj/upper_crossarm/OUT_UPPER_CROSSARM').geometry().boundingBox()\nif c+gap/2+f>=arm.minvec()[0]-.03 and c-gap/2-f<=arm.maxvec()[0]+.03:raise ValueError('Seam overlaps upper crossarm support band')"
 new_guard="for arm_path in "+repr((ARM,rear_arm.path()))+":\n arm=hou.node(arm_path).geometry().boundingBox()\n if c+gap/2+f>=arm.minvec()[0]-.03 and c-gap/2-f<=arm.maxvec()[0]+.03:raise ValueError('Seam overlaps upper crossarm support band')"
 assert old_guard in code;seam.parm('python').set(code.replace(old_guard,new_guard))
 framecheck.STATION=STATION
 lower={p:framecheck.inspect(rack.geometry(),hou.node(p).geometry()) for p in frames};assert all(r['passed'] for r in lower.values()),lower
 holes=framecheck.verify_crossarm(rack.geometry())
 upper_joints=joints(rear_arm.geometry(),[hou.node(p).geometry() for p in frames]);assert upper_joints['passed'],upper_joints
 topologies={p:topo(hou.node(p).geometry()) for p in new_paths}
 seating=bearing([hou.node(ARM).geometry(),rear_arm.geometry()],hou.node(DUCT).geometry());assert seating['passed'],seating
 assert seam_check(hou.node(DUCT).geometry())['passed'] and passage(hou.node(DUCT).geometry())['passed']
 after=record(BASE+new_paths);after_parts=allparts(after);delta=compare(before_parts,after_parts)
 assert set(delta['removed'])==set(RETIRED) and set(delta['changed'])==set(BEAMS) and len(delta['unchanged'])==212 and len(delta['added'])==3,delta
 for path in BASE:
  assert before[path]['matrix']==after[path]['matrix'] and before[path]['material']==after[path]['material']
 # Read per-part bounds once; expected end/bearing contacts handled above.
 boxes={}
 for path in BASE:
  for prim in hou.node(path).geometry().prims():
   box=boxes.setdefault(prim.attribValue('name'),[[float('inf')]*3,[-float('inf')]*3])
   for v in prim.vertices():
    for i,value in enumerate(v.point().position()):box[0][i]=min(box[0][i],value);box[1][i]=max(box[1][i],value)
 clear={}
 for path in new_paths:
  exclude=set(BEAMS) if path in frames else {'upper_duct_left','upper_duct_right'}
  near=min((separation(bounds(hou.node(path).geometry()),b),name) for name,b in boxes.items() if name not in exclude);assert near[0]>.001,near
  clear[path]=dict(part=near[1],aabb_clearance_lower_bound=near[0])
 negative={}
 for label,translation in [('rear_arm_low',(0,-.006,0)),('rear_arm_high',(0,.003,0)),('rear_arm_wrong_x',(.15,0,0))]:
  bad=hou.Geometry();bad.merge(rear_arm.geometry());bad.transform(hou.hmath.buildTranslate(translation));result=bearing([hou.node(ARM).geometry(),bad],hou.node(DUCT).geometry())
  # Wrong X can still support duct, but cannot contact the fixed uprights.
  negative[label]=not result['passed'] or not joints(bad,[hou.node(p).geometry() for p in frames])['passed']
 negative['missing_second_station']=not bearing([hou.node(ARM).geometry()],hou.node(DUCT).geometry())['passed']
 bad=hou.Geometry();bad.merge(hou.node(frames[0]).geometry());bad.transform(hou.hmath.buildTranslate((0,0,-.006)))
 negative['rear_upright_gap']=not framecheck.inspect(rack.geometry(),bad)['passed'];assert all(negative.values()),negative
 for x in (-.6,.6):
  seam.parm('seam_x').set(x)
  try:seam.cook(force=True)
  except hou.OperationFailed:pass
  assert seam.errors(),('Seam support guard did not reject',x)
 seam.parm('seam_x').set(-.15);hou.node(DUCT).cook(force=True)
 control=hou.node(CONTROL);control.parm('tier_y').set(.58)
 assert bearing([hou.node(ARM).geometry(),rear_arm.geometry()],hou.node(DUCT).geometry())['passed']
 assert joints(rear_arm.geometry(),[hou.node(p).geometry() for p in frames])['passed']
 control.parm('tier_y').set(.55);assert record(BASE+new_paths)==after
 parent.layoutChildren()
 cam=hou.node('/obj/accept_camera');cam.parm('orthowidth').set(4.15);aim(cam,(0,.45,0),(5,3,-6));hou.hipFile.save(str(out/'assembly.hip'))
 cam.parm('orthowidth').set(3.5);aim(cam,(0,.45,0),(0,6,.001));hou.hipFile.save(str(out/'top.hip'))
 cam.parm('orthowidth').set(3.4);aim(cam,(0,.40,0),(.001,.06,-6));hou.hipFile.save(str(out/'longitudinal.hip'))
 iso=parent.createNode('python','isolate_both_lower_crossarms');iso.setInput(0,rack);iso.parm('python').set('import hou\ng=hou.pwd().geometry();g.clear();g.merge(hou.pwd().inputs()[0].geometry())\ng.deletePrims([p for p in g.prims() if p.attribValue("name") not in '+repr(BEAMS+tuple('rack_pos_0'+s for s in ('_web','_lip_-1','_lip_1')))+'])');iso.setDisplayFlag(True);iso.setRenderFlag(True)
 hou.node(DUCT).parent().setDisplayFlag(False);cam.parm('orthowidth').set(3.1);aim(cam,(0,.40,0),(4,2,-5));hou.hipFile.save(str(out/'frames-only.hip'))
 # Show only rear frame and both duct segments for an unobstructed bearing review.
 for path in FRAME_PATHS+(ARM,):hou.node(path).parent().setDisplayFlag(False)
 parent.setDisplayFlag(False);hou.node(DUCT).parent().setDisplayFlag(True)
 cam.parm('orthowidth').set(1.1);aim(cam,(rear_x,.54,.1),(-2,-.9,-2))
 light=hou.node('/obj').createNode('hlight::2.0','rear_bearing_review_light');light.parm('light_type').set(2);light.parmTuple('areasize').set((2,2));light.parm('light_intensity').set(.65);aim(light,(rear_x,.55,.1),(2,-1.2,2))
 hou.hipFile.save(str(out/'rear-bearing.hip'))
 hou.hipFile.load(str(out/'assembly.hip'),suppress_save_prompt=True);assert record(BASE+new_paths)==after
 assert sha==hashlib.sha256(source.read_bytes()).hexdigest() and libsha==hashlib.sha256(library.read_bytes()).hexdigest()
 report=dict(passed=True,source=str(source),source_sha256=sha,source_library=str(library),source_library_sha256=libsha,library=str(delivery),asset_path=asset_path,
  before=before,outputs=after,inheritance=delta,retained_count=212,total_parts=len(after_parts),rear_x=rear_x,lower_checks=lower,upper_checks=upper_joints,
  lower_holes=holes,topology=topologies,bearing=seating,clearances=clear,counterexamples=negative,shared_height_reset=True,both_seam_guards=True,saved_reopened=True,
  scope='Two estimated longitudinal stations, existing pitch reused. Hidden brackets, anchors, load capacity and remaining upper utilities unmodeled')
 (out/'native-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('passed','rear_x','retained_count','total_parts','bearing','counterexamples')}),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);build(parser.parse_args())
