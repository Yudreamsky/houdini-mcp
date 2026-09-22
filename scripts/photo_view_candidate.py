"""Camera-only qualitative photo comparison; dimensions are not reconstructed."""
import hashlib,json,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from paired_frame_candidate import aim,detailed

def build():
 source=ROOT/'assets/paired-stations-v01/candidate-01/assembly.hip'
 out=ROOT/'assets/upper-assembly-v01/camera-02';out.mkdir(parents=True,exist_ok=False)
 accepted=json.loads((ROOT/'evidence/render-jobs/8482f9f81f354c25a0c51f910fec2c4a/request.json').read_text())
 sha=hashlib.sha256(source.read_bytes()).hexdigest();assert sha==accepted['scene_sha256']
 report=json.loads(source.with_name('native-report.json').read_text())
 hou.hipFile.load(str(source),suppress_save_prompt=True)
 for path,record in report['outputs'].items():assert detailed(hou.node(path).geometry())==record['parts']
 cam=hou.node('/obj/accept_camera');cam.parm('projection').set(0);cam.parm('focal').set(100)
 aim(cam,(0,.37,0),(-3,-5.5,5.1))
 # A broad review fill makes underside connections readable, without material edits.
 light=hou.node('/obj').createNode('hlight::2.0','photo_underfill')
 light.parm('light_type').set(2);light.parmTuple('areasize').set((4,4));light.parm('light_intensity').set(4)
 aim(light,(0,.35,0),(-1,-3,3))
 environment=hou.node('/obj').createNode('envlight','photo_environment');environment.parm('light_intensity').set(.4)
 hou.hipFile.save(str(out/'photo-view.hip'))
 for path,record in report['outputs'].items():assert detailed(hou.node(path).geometry())==record['parts']
 result=dict(passed=True,source=str(source),source_sha256=sha,unchanged_parts=218,library=report['library'],camera=dict(projection='perspective',focal_mm=100,target=[0,.37,0],offset=[-3,-5.5,5.1]),scope='Qualitative underside view only. No solved photo camera or measured dimensions.')
 (out/'native-report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':build()
