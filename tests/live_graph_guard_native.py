"""hython -m tests.live_graph_guard_native: graph mutations in a disposable scene."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import hou

from hlab import live_graph as graph


def denied(action, fragment):
    try:
        action()
    except ValueError as exc:
        assert fragment in str(exc), exc
    else:
        raise AssertionError("Unexpectedly accepted: " + fragment)


def put(n, parm, value, **extra):
    return graph.edit_one(graph.Batch(), dict(op="set", path=n.path(), parm=parm, value=value, **extra), "test", set())


def check(directory):
    net = hou.node("/obj").createNode("geo",run_init_scripts=False)
    a,b,c,d = [net.createNode("box", name) for name in ("a","b","c","d")]
    for func in ("run","runb","rune","execute","executeb","executee","systemRAW","eval","evals","pythonexprs"):
        denied(lambda:put(a,"tx",func+'("echo 23")',expression="hscript"), "Code-capable")
    denied(lambda:put(a,"tx","23",expression="python"), "Code-capable")
    font = net.createNode("font")
    denied(lambda:put(font,"text",'prefix `run("echo 23")`'), "Code-capable")
    denied(lambda:put(font,"text",r'\`dummy`run("echo 23")`'), "Code-capable")
    cache = net.createNode("filecache::2.0")
    cache.parm("tpostwrite").set(1)
    denied(lambda:put(cache, "postwrite", "echo bad"), "Code-capable")
    para = hou.StringParmTemplate("description", "Description", 1)
    a.addSpareParmTuple(para)
    put(a, "description", 'The command run() is mentioned as text')
    put(font,"text",'frame `$FF`')
    assert font.evalParm("text")=="frame 1"
    put(a,"tx",'sin($FF) + ch("sizey")',expression="hscript")
    assert a.evalParm("tx") > 1
    wrangle = net.createNode("attribwrangle")
    code = 's@label = "run() in VEX text"; @P.y += 1;'
    put(wrangle,"snippet",code)
    assert wrangle.parm("snippet").unexpandedString()==code
    script = net.createNode("python")
    denied(lambda:put(script,"python","a = 12"),"Code-capable")
    audit = Path(directory)/"audit"/"graph-code.jsonl"
    assert not audit.exists()
    with patch.dict(os.environ,{"HOUDINI_RESEARCH_ALLOW_CODE":"1"}):
        put(script,"python","a = 12")
        put(b,"tx",'run("echo 23")',expression="hscript")
        assert b.evalParm("tx")==23
    events=[json.loads(line) for line in audit.read_text().splitlines()]
    for row, parm, value in zip(events,[script.parm("python"),b.parm("tx")],["a = 12",'run("echo 23")'],strict=True):
        assert row["time"] and row["path"]==parm.path() and row["sha256"]==hashlib.sha256(value.encode()).hexdigest()
    p=c.parm("ty")
    for frame, value in ((1,2),(5,10)):
        key=hou.Keyframe();key.setFrame(frame);key.setValue(value);p.setKeyframe(key)
    p.setKeyframeExtrapolation(True,hou.parmExtrapolate.Cycle)
    p.setKeyframeExtrapolation(False,hou.parmExtrapolate.Slope)
    d.parm("tz").setExpression('ch("../c/ty")',hou.exprLanguage.Hscript)
    before=[p.evalAtFrame(f) for f in (-3,1,5,9,21)]
    denied(lambda:put(c,"ty",9), "Animated or linked")
    group=net.createNetworkBox()
    group.addItem(a)
    group.addItem(b)
    merge=net.createNode("merge")
    for source in (a,b,c,d):
        merge.setNextInput(source)
    dot=net.createNetworkDot()
    dot.setInput(c)
    merge.setInput(2,dot)
    expected=[v.path() for v in merge.inputs()]
    edit=dict(op="set",path=c.path(),parm="ty",value=12,replace_expression=True)
    disconnect=dict(op="connect",path=merge.path(),input=1,source=None)
    remove=dict(op="delete",path=b.path())
    missing=dict(op="connect",path=merge.path(),source=net.path()+"/missing")
    denied(lambda:graph.edit([edit,disconnect,remove,missing],allow_delete=[b.path()]),"Step 4 rolled back")
    assert [v.path() for v in merge.inputs()] == expected
    assert merge.inputConnections()[2].inputItem() == dot
    assert hou.node(expected[1]).parentNetworkBox()==group
    assert [p.evalAtFrame(f) for f in (-3,1,5,9,21)] == before
    assert d.parm("tz").getReferencedParm()==p
    batch=graph.Batch()
    graph.edit_one(batch,remove,"node delete",{expected[1]})
    assert [v.path() for v in merge.inputs()]==[expected[i] for i in (0,2,3)]
    batch.undo();batch.redo();batch.undo()
    assert [v.path() for v in merge.inputs()]==expected and hou.node(expected[1]).parentNetworkBox()==group
    print("PASS HScript aliases, callback and Python gating/audit, modeling expressions/VEX, animated extrapolation, multi-input wiring, network box, undo/redo")


def check_creation(directory):
    cam="/obj/CAMTEST"
    lens=dict(resx=900,resy=2000,focal=110,projection=1,orthowidth=150)
    steps=graph.edit([dict(op="create",path=cam,type="cam"),*[dict(op="set",path=cam,parm=k,value=v) for k,v in lens.items()],
                      dict(op="create",path="/obj/GEOTEST",type="geo"),
                      dict(op="set",path="/obj/GEOTEST",parm="vm_rendersubd",value=True)])["steps"]
    assert steps[0]["init_scripts"] and steps[6]["init_scripts"], steps
    assert {k:hou.node(cam).evalParm(k) for k in lens}==lens
    assert all(hou.node(cam).parm(k) for k in ("aperture","near","far"))
    bare={p.name() for p in hou.node("/obj").createNode("geo",run_init_scripts=False).parms()}
    added=sorted(p.name() for p in hou.node("/obj/GEOTEST").parms() if p.name().startswith("vm_") and p.name() not in bare)
    assert len(added)>=20 and "vm_rendervisibility" in added, added
    # An asset from outside $HFS stays gated and is created without its own scripts.
    source=hou.node("/obj").createNode("subnet")
    asset=source.createDigitalAsset(name="mcp_probe_asset",hda_file_name=str(Path(directory)/"probe.hda"),min_num_inputs=0,max_num_inputs=0)
    definition=asset.type().definition()
    definition.addSection("OnCreated",'kwargs["node"].setUserData("created_by_script","1")')
    definition.setExtraFileOption("OnCreated/IsPython",True)
    assert hou.node("/obj").createNode("mcp_probe_asset").userData("created_by_script")=="1"
    denied(lambda:graph.edit([dict(op="create",path="/obj/EXTERNAL",type="mcp_probe_asset")]),"Code-capable")
    with patch.dict(os.environ,{"HOUDINI_RESEARCH_ALLOW_CODE":"1"}):
        step=graph.edit([dict(op="create",path="/obj/EXTERNAL",type="mcp_probe_asset")])["steps"][0]
    assert step["init_scripts"] is False and hou.node("/obj/EXTERNAL").userData("created_by_script") is None
    print(f"PASS camera lens and {len(added)} vm_ parameters set in their creating batch; external asset scripts stay off")


if __name__=="__main__":
    assert not hou.isUIAvailable()
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{"HOUDINI_RESEARCH_ALLOW_CODE":"0","HOUDINI_RESEARCH_HOME":tmp}):
        check(tmp)
        check_creation(tmp)
