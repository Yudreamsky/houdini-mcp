"""Run hython -m tests.live_study_native in a disposable scene; no existing window is touched."""
import os
import tempfile
from unittest.mock import patch

import hou

from hlab import scene
from hlab.live_study import run
from hlab.storage import details, search, stored


def check():
    root = hou.node("/obj")
    recipe = details(search(topic="fireworks", kind="recipe")["cards"][0]["id"])
    info = recipe["details"]
    fixture = scene.load_checkpoint(stored("bundles", info["bundle"]+".cpio"))
    hou.session.hr_active_path = fixture.path()
    scatter = fixture.node("SCATTER")
    trails = fixture.node("TRAILS")
    hou.setFrame(25)
    parm = scatter.parm("npts")
    value = parm.eval()

    # Use exactly the same reference algorithm as the original fixture. Optical evidence is tested separately in a GUI.
    hashes=[]
    for n in [32,96,192]:
        parm.set(n);hou.setFrame(36);hashes.append(scene.metrics()["output_sha256"])
    parm.set(value);hou.setFrame(25)
    result=run("sweep", scatter.path(), "npts", [32,96,192], 36, trails.path(), topic="live-test")
    assert [q["metrics"]["output_sha256"] for q in result["samples"]]==hashes
    assert result["observed_change"] and result["baseline_restored"] and parm.eval()==value and hou.frame()==25
    old=details(result["id"]);assert old["kind"]=="experiment" and old["details"]["process"]=="live"
    assert run("sweep",scatter.path(),"npts",[32,96],36, fixture.node("SOURCE").path(),
               expect_change=True,topic="live-test")["gap"]
    no_response = run("sweep", scatter.path(), "npts", [32,96], 36, fixture.node("SOURCE").path())
    assert no_response["gap"] and no_response["observation"]

    obj=root.createNode("geo", run_init_scripts=False)
    box=obj.createNode("box");box.parm("tx").setExpression("$FF",hou.exprLanguage.Hscript)
    comp=run("compare",box.path(),variants={"wide":{"sizex":2.0},"tall":{"sizey":3.0}},frames=[3,8])
    assert comp["candidates"]["wide"]["parameters"]=={"sizex":2.0,"sizey":1.0}
    assert comp["candidates"]["tall"]["parameters"]=={"sizex":1.0,"sizey":3.0}
    assert len(comp["candidates"]["wide"]["samples"])==2 and comp["observed_change"]
    motion=run("motion",box.path(),changes={"sizey":2},frames=[2,4,7])
    assert motion["observed_change"] and [round(sample["metrics"]["bbox_min"][0],2) for sample in motion["samples"]]==[1.5,3.5,6.5]
    assert hou.frame()==25 and box.evalParm("sizey")==1
    try:run("sweep",box.path(),"tx",[1,2])
    except ValueError:pass
    else:raise AssertionError("Animated parameter was modified")

    # Packed data also changes when its pivot positions remain static.
    packed=box.createOutputNode("pack")
    answer=run("sweep",box.path(),"sizex",[1,2],witness=packed.path())
    assert answer["observed_change"] and answer["baseline_restored"]
    guard=box.createOutputNode("python");guard.parm("python").set(
        "import hou\nif hou.pwd().inputs()[0].evalParm('sizex') > 2: raise hou.NodeError('injected cook failure')")
    try:run("sweep",box.path(),"sizex",[1.5,3],witness=guard.path())
    except ValueError as exc:assert "injected cook failure" in str(exc)
    else:raise AssertionError("A broken witness was reported as successful")
    assert box.evalParm("sizex")==1 and hou.frame()==25
    print("PASS legacy TRAILS hashes, variant isolation, motion, packed changes, gap evidence, animation guard and failed-cook restoration")


if __name__=="__main__":
    assert not hou.isUIAvailable()
    with tempfile.TemporaryDirectory(prefix="live-study-acceptance-") as directory, patch.dict(os.environ,{"HOUDINI_RESEARCH_HOME":directory}):
        check()
