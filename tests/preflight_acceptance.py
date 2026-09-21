"""Fresh hython: preflight_acceptance.py NEW_OUTPUT_DIR; actual read-only guards."""
import json
import sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local.procedural_assets import upsert,preflight

out=Path(sys.argv[1]).resolve()
if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty headless hython')
out.mkdir(parents=True,exist_ok=False)
def snapshot():
    return dict(nodes=[n.path() for n in hou.node('/').allSubChildren()],dirty=hou.hipFile.hasUnsavedChanges(),
                libraries=sorted(hou.hda.loadedFiles()),cache=sorted(str(p) for p in (ROOT/'.runtime/asset-library').glob('*')))

before=snapshot();result=preflight('new-default')
assert result['ready'] and result['recipe']=='pipe_support_sample' and result['will_create']
assert snapshot()==before
errors=preflight('new-elbow',{'diameter':.6,'bend_radius':.6,'hanger_height':.7},'pipe_elbow_sample')
assert not errors['ready'] and len(errors['errors'])==2
assert snapshot()==before
first=upsert('guard-test',recipe='pipe_elbow_sample');node=hou.node(first['path'])
valid=preflight('guard-test',{'inlet_length':4.2})
assert valid['ready'] and valid['recipe']=='pipe_elbow_sample' and valid['parameters']['outlet_length']==1.8
checks=[]
def rejected(label,changes):
    before=snapshot();values={p.name():p.eval() for p in node.parms()}
    plan=preflight('guard-test',changes)
    assert not plan['ready'],label
    try:upsert('guard-test',changes)
    except ValueError:pass
    else:raise AssertionError(label+' write unexpectedly accepted')
    assert before==snapshot() and values=={p.name():p.eval() for p in node.parms()},label
    checks.append(dict(case=label,errors=plan['errors']))
node.parm('inlet_length').setExpression('2.4');rejected('animated',{'inlet_length':3.6})
assert node.parm('inlet_length').expression()=='2.4'
node.parm('inlet_length').deleteAllKeyframes();node.parm('inlet_length').set(2.4)
node.parm('inlet_length').lock(True);rejected('locked',{'inlet_length':3.6});node.parm('inlet_length').lock(False)
node.allowEditingOfContents();rejected('unlocked_hda',{'inlet_length':3.6});node.matchCurrentDefinition()
digest=node.userData('workai_recipe_sha256');node.setUserData('workai_recipe_sha256','outdated');rejected('recipe_version',{});node.setUserData('workai_recipe_sha256',digest)
node.parent().setUserData('workai_instance_id','foreign');rejected('ownership',{});node.parent().setUserData('workai_instance_id','guard-test')
before=snapshot();conflict=preflight('guard-test',recipe='pipe_support_sample');assert not conflict['ready'];assert before==snapshot()
node.parm('inlet_length').set(3.0)
# Preflight is not a reservation: changed current state is re-read on write.
updated=upsert('guard-test',{'outlet_length':3.6})
assert updated['parameters']['inlet_length']==3.0 and updated['recipe']=='pipe_elbow_sample'
report=dict(passed=True,mode='headless HOM',readonly_new_instance=result,combined_violations=errors,
            guards=checks,explicit_conflict=conflict,write_rereads_current_parameters=True)
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
