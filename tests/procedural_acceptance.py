"""Run with hython in a fresh headless process: procedural_acceptance.py OUTPUT_DIR.

This verifies real HOM/HDA behavior, not MCP transport or GUI previews.
"""
import json
import shutil
import sys
from pathlib import Path
import hou
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local.procedural_assets import upsert
from houdini_mcp_local.sample_inspection import inspect

out=Path(sys.argv[1]).resolve()
if hou.isUIAvailable() or hou.node('/obj').children(): raise RuntimeError('Use a fresh headless hython process with no scene objects')
if out.exists(): raise FileExistsError('Use a new acceptance output directory')
out.mkdir(parents=True)
first=upsert('acceptance')
node=hou.node(first['path'])
hou.hipFile.save(str(out/'checkpoint.hip'))
again=upsert('acceptance')
assert not again['created'] and not again['changed']
# Hython can report unsaved changes immediately after save; clean-state
# preservation is separately checked in the real GUI MCP acceptance.
assert again['check']['geometry_sha256']==first['check']['geometry_sha256']
for parameters in ({'diameter':.1,'wall':.03},{'segments':25},{'unknown':1}):
    try: upsert('acceptance',parameters)
    except ValueError: pass
    else: raise AssertionError('Invalid input accepted')
assert inspect(node.path())['geometry_sha256']==first['check']['geometry_sha256']
node.allowEditingOfContents()
try: upsert('acceptance',{'length':3.6})
except ValueError: pass
else: raise AssertionError('Unlocked contents overwritten')
node.matchCurrentDefinition()
node.parm('length').setExpression('2.4')
try: upsert('acceptance',{'length':3.6})
except ValueError: pass
else: raise AssertionError('Expression overwritten')
assert node.parm('length').expression()=='2.4'
node.parm('length').deleteAllKeyframes();node.parm('length').set(2.4)
grown=upsert('acceptance',{'diameter':.5,'length':3.6})
assert grown['check']['passed'] and grown['check']['measurements']['support_count']==4
assert {p['name'] for p in first['check']['parts']} <= {p['name'] for p in grown['check']['parts']}
final=upsert('acceptance',{'diameter':.32,'length':2.4})
library=out/Path(final['library']).name;shutil.copy2(final['library'],library)
hou.hda.installFile(str(library))
for d in hou.hda.definitionsInFile(str(library)):d.setIsPreferred(True)
hip=out/'sample.hip';hou.hipFile.save(str(hip));hou.hipFile.load(str(hip),suppress_save_prompt=True)
reopened=inspect(final['path']);assert reopened['passed'] and reopened['geometry_sha256']==final['check']['geometry_sha256']
report={'passed':True,'houdini':hou.applicationVersionString(),'mode':'headless HOM, not MCP/GUI',
        'library':str(library),'hip':str(hip),'geometry_sha256':reopened['geometry_sha256'],
        'part_count':reopened['part_count'],'measurements':reopened['measurements']}
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
