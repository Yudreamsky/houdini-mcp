"""Native failure/rollback tests using an isolated delivered HIP, never the GUI."""
import json,sys
from pathlib import Path
from unittest.mock import patch
import hou
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from houdini_mcp_local import asset_ops,tier_asset_ops
OUT=ROOT/'evidence/upper-assembly-v01';ASSET=ROOT/'assets/upper-assembly-v01/candidate-02'

def main():
 hou.hipFile.load(str(ASSET/'assembly.hip'),suppress_save_prompt=True)
 node=hou.node('/obj/two_tier_assembly/asset');module=node.hdaModule();base=node.node('snapshot').geometry()
 spec=module.manifest(node);baseline=tier_asset_ops.inspect(node);assert baseline['passed']
 negatives={}
 for label in ('missing_identity','rear_arm_offset','fixed_pipe_motion'):
  bad=hou.Geometry();bad.merge(node.geometry())
  if label=='missing_identity':
   p=next(p for p in bad.prims() if p.attribValue('name')=='rear_upper_crossarm');p.setAttribValue('name','')
  else:
   name='rear_upper_crossarm' if label=='rear_arm_offset' else 'pipe1_left'
   if label=='fixed_pipe_motion': name=next(n for n in spec['face_counts'] if 'pipe1' in n and 'pipe' in n)
   indices={v.point().number() for p in bad.prims() if p.attribValue('name')==name for v in p.vertices()};assert indices
   for p in bad.points():
    if p.number() in indices:q=p.position();q[1]+=.006;p.setPosition(q)
  result=module.inspect_geometry(bad,base,spec,.55);assert not result['passed'];negatives[label]=result['issues']
 # Houdini clamps strict bounds even for this expression; MCP rejects out of range
 # instead of silently accepting a different requested value.
 node.parm('tier_y').setExpression('0.9',language=hou.exprLanguage.Hscript)
 assert node.evalParm('tier_y')==.8
 assert tier_asset_ops.inspect(node)['passed']
 try:asset_ops.set_parameters(node.path(),{'tier_y':.58})
 except ValueError as error:assert 'Animated' in str(error)
 else:raise AssertionError('Expression channel accepted')
 node.parm('tier_y').deleteAllKeyframes();node.parm('tier_y').set(.55);assert tier_asset_ops.inspect(node)==baseline
 negatives['direct_strict_clamp_and_expression_edit_rejected']=True
 # Simulate an inspection failure after successful native cook, verify real rollback.
 actual=tier_asset_ops.inspect;trace=[]
 def fail_after_write(n):
  value=actual(n);trace.append(n.evalParm('tier_y'))
  if n.evalParm('tier_y')==.6:raise RuntimeError('Injected post-cook inspection failure')
  return value
 with patch.object(tier_asset_ops,'inspect',side_effect=fail_after_write):
  try:asset_ops.set_parameters(node.path(),{'tier_y':.6})
  except ValueError as error:assert 'verified restored' in str(error)
  else:raise AssertionError('Fault injection did not reject update')
 assert trace==[.55,.6,.55] and actual(node)==baseline
 # Unlocked internals are outside this narrow managed contract.
 probe=node.parent().createNode(node.type().name(),'unlocked_probe');probe.allowEditingOfContents()
 try:asset_ops.set_parameters(probe.path(),{'tier_y':.58})
 except ValueError as error:assert 'locked' in str(error)
 else:raise AssertionError('Unlocked asset accepted')
 probe.destroy()
 result=dict(passed=True,geometry_counterexamples=negatives,injected_postcook_rollback_trace=trace,rollback_geometry_verified=True,unlocked_asset_rejected=True)
 (OUT/'native-negative-tests.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
