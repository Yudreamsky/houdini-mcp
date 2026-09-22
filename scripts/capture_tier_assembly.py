"""Package the accepted fixed assembly as a portable, one-parameter snapshot HDA."""
import collections,hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from paired_frame_candidate import detailed,aim
from houdini_mcp_local import tier_assembly

def build():
 source=ROOT/'assets/upper-assembly-v01/camera-02/photo-view.hip'
 out=ROOT/'assets/upper-assembly-v01/candidate-02';out.mkdir(parents=True,exist_ok=False)
 previous=json.loads((ROOT/'assets/paired-stations-v01/candidate-01/native-report.json').read_text())
 hou.hipFile.load(str(source),suppress_save_prompt=True)
 merged=hou.Geometry();before={};material_promotions={}
 for path,expected in previous['outputs'].items():
  node=hou.node(path);assert detailed(node.geometry())==expected['parts']
  assert max(abs(a-b) for a,b in zip(node.parent().worldTransform().asTuple(),hou.Matrix4(1).asTuple()))<1e-9
  capture=hou.Geometry();capture.merge(node.geometry())
  if not capture.findPrimAttrib('shop_materialpath'):capture.addAttrib(hou.attribType.Prim,'shop_materialpath','')
  for primitive in capture.prims():
   if not primitive.attribValue('shop_materialpath'):
    value=node.parent().parm('shop_materialpath').eval();assert hou.node(value)
    primitive.setAttribValue('shop_materialpath',value);material_promotions[primitive.attribValue('name')]=value
  before.update(detailed(capture));merged.merge(capture)
 assert detailed(merged)==before,'Merged snapshot changed component attributes'
 assert len(before)==218
 code=(ROOT/'src/houdini_mcp_local/tier_assembly.py').read_text()
 spec=dict(kind=tier_assembly.KIND,base_height=.55,height_min=.45,height_max=.80,
           duct_width=.55,duct_center_z=.10,face_counts=dict(collections.Counter(merged.primStringAttribValues('name'))),
           source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source=str(source),
           source_parts=before,moving=list(tier_assembly.MOVING),stations=tier_assembly.STATIONS,
           interpretation='Photo-guided estimates. One variable height; all other dimensions captured, not procedural.')
 digest=hashlib.sha256((code+json.dumps(spec,sort_keys=True)).encode()).hexdigest()[:12]
 typename='workai::two_tier_snapshot::1.0.'+digest;library=out/('workai_two_tier_'+digest+'.hda')
 obj=hou.node('/obj').createNode('geo','two_tier_assembly',run_init_scripts=False)
 sub=obj.createNode('subnet','asset');stash=sub.createNode('stash','snapshot');stash.parm('stash').set(merged)
 python=sub.createNode('python','height_link');python.setInput(0,stash)
 python.parm('python').set('hou.pwd().parent().hdaModule().cook(hou.pwd())')
 output=sub.createNode('null','OUT');output.setInput(0,python);output.setDisplayFlag(True);output.setRenderFlag(True)
 asset=sub.createDigitalAsset(name=typename,hda_file_name=str(library),description='WORKAI Two-Tier Snapshot',min_num_inputs=0,max_num_inputs=0)
 definition=asset.type().definition();group=hou.ParmTemplateGroup()
 group.append(hou.FloatParmTemplate('tier_y','Upper tier height (m)',1,default_value=(.55,),min=.45,max=.80,min_is_strict=True,max_is_strict=True))
 definition.setParmTemplateGroup(group);definition.addSection('PythonModule',code)
 definition.addSection('AssemblyManifest',json.dumps(spec,sort_keys=True))
 definition.addSection('Help','Captured 218-part visual assembly. Only upper-tier height is editable (0.45–0.80 m). Four parts move; 214 remain fixed. HDA embeds snapshot and code. Materials are supplied by the companion HIP. Estimates are not engineering specifications.')
 asset.matchCurrentDefinition();asset.setDisplayFlag(True);asset.setRenderFlag(True)
 check=asset.hdaModule().inspect(asset);assert check['passed'],check
 assert detailed(asset.geometry())==before
 # Retire old scene objects from this candidate, retaining the original HIP as rollback.
 for path in previous['outputs']:
  node=hou.node(path)
  if node is not None:node.parent().destroy()
 assert len([o for o in hou.node('/obj').children() if o.type().name()=='geo' and o.isDisplayFlagSet()])==1
 # A new instance contains its own mesh and height channel; no external node paths.
 copy=obj.createNode(typename,'copy_probe');copy.parm('tier_y').set(.58)
 copy_check=copy.hdaModule().inspect(copy);assert copy_check['passed'];copy.destroy()
 asset.setDisplayFlag(True);asset.setRenderFlag(True)
 hou.hipFile.save(str(out/'photo-view.hip'))
 cam=hou.node('/obj/accept_camera');aim(cam,(0,.37,0),(3,-5.5,-5.1))
 aim(hou.node('/obj/photo_underfill'),(0,.35,0),(1,-3,-3))
 hou.node('/obj/photo_underfill').parm('light_intensity').set(1.2)
 hou.hipFile.save(str(out/'photo-direction.hip'))
 aim(hou.node('/obj/photo_underfill'),(0,.35,0),(-1,-3,3))
 hou.node('/obj/photo_underfill').parm('light_intensity').set(4)
 cam=hou.node('/obj/accept_camera');cam.parm('projection').set(1);cam.parm('orthowidth').set(4.15);aim(cam,(0,.45,0),(5,3,-6))
 hou.hipFile.save(str(out/'assembly.hip'))
 hou.hipFile.load(str(out/'assembly.hip'),suppress_save_prompt=True)
 asset=hou.node('/obj/two_tier_assembly/asset');assert asset.matchesCurrentDefinition()
 assert detailed(asset.geometry())==before
 result=dict(passed=True,source=str(source),source_sha256=spec['source_sha256'],library=str(library),asset_path=asset.path(),
             node_type=typename,parts=before,inspection=check,copy_at_580=copy_check,component_count=218,unchanged_parts=218,
             saved_reopened=True,material_promotions=material_promotions,scope=spec['interpretation'])
 (out/'native-report.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ('passed','library','component_count','saved_reopened')}),flush=True)
if __name__=='__main__':build()
