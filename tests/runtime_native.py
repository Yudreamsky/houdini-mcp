"""Windows/Houdini integration checks for worker reuse, contamination and version evidence.

Run python -m tests.runtime_native. All writable HIPs, HDA definitions and evidence live in a temporary directory.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE = "hr_test::runtime_contamination::1.0"


def fixture(folder):
    import hou

    def make_asset():
        geo = hou.node("/obj").createNode("geo", run_init_scripts=False)
        subnet = geo.createNode("subnet", "definition")
        subnet.createNode("box").setDisplayFlag(True)
        asset = subnet.createDigitalAsset(name=TYPE, hda_file_name=str(folder/"marker.hda"))
        asset.destroy()
        hou.hda.uninstallFile(str(folder/"marker.hda"))
        hou.hipFile.clear(suppress_save_prompt=True)

    make_asset()
    upper = hou.node("/obj").createNode("geo", "upper", run_init_scripts=False)
    box = upper.createNode("box")
    upper.parm("ty").set(2)
    probe = box.createOutputNode("python")
    probe.parm("python").set(
        "import hou, os\nfrom pathlib import Path\n"
        f"hou.hda.installFile({(folder/'marker.hda').as_posix()!r})\n"
        f"assert hou.nodeType(hou.sopNodeTypeCategory(), {TYPE!r})\n"
        f"Path({(folder/'observed-pid.txt').as_posix()!r}).write_text(str(os.getpid()))")
    probe.setDisplayFlag(True)
    lower = hou.node("/obj").createNode("geo", "lower", run_init_scripts=False)
    lower.createNode("box").setDisplayFlag(True)
    for height, name in ((2,"one"),(4,"three")):
        upper.parm("ty").set(height)
        hou.hipFile.save(str(folder/(name+".hip")), save_to_recent_files=False)
    hou.hipFile.load(str(ROOT/"examples/rain/Rain.hip"), suppress_save_prompt=True)
    node = hou.node("/obj/RAIN/Wave_1")
    guard = node.inputs()[0].createOutputNode("python", "Assert_fresh_hda_registry")
    guard.parm("python").set(
        f"import hou\nassert hou.nodeType(hou.sopNodeTypeCategory(),{TYPE!r}) is None, 'foreign HDA leaked'")
    node.setInput(0, guard)
    hou.hipFile.save(str(folder/"guarded.hip"),save_to_recent_files=False)


def acceptance(folder):
    import shutil
    from unittest.mock import patch
    from hlab.animation_gap import run as gap
    from hlab.runtime import discover
    from hlab.server import learn, node_lab
    from hlab.sop_lab import verify_recipe
    from hlab.storage import details, read, search, write
    from hlab.worker_pool import pool

    def native(action, **kw):
        return json.loads(node_lab(action=action, **kw)[0].text)

    def clone_record(key):
        row = details(key)
        path = folder/"records"/key
        write(path/"card.json", {k:v for k,v in row.items() if k!="details"})
        write(path/"details.json", row["details"])
        return path/"details.json"

    hython = discover().hython
    subprocess.run([str(hython),str(Path(__file__)), "--fixture",str(folder)],check=True)
    query = ("sample:mechanisms/Climbing-support-transfer.hip", "/obj/CLIMBING_STUDY/New_section", "/obj/CLIMBING_STUDY/Cart",1379,1454,"y",.228,None,"")
    times=[];pids=[]
    for i in range(3):
        start=time.monotonic()
        row=gap(*query)
        times.append(round(time.monotonic()-start,3));pids.append(row["process_pid"])
        assert row["status"]=="passed" and row["measured_frames"]==76 and abs(row["lowest"]["gap"]-.23)<1e-5
    assert len(set(pids))==1 and max(times[1:])<times[0], (times,pids)
    pool.proc.kill();pool.proc.wait()
    assert gap(*query)["process_pid"]!=pids[0]
    # Check actual concurrent license availability while the GUI is untouched. Normal fresh dispatch releases warm first.
    subprocess.run([str(hython),"-c","import hou; print('concurrent fresh:',hou.applicationVersionString())"],timeout=45,check=True)
    target=folder/"edited.hip";shutil.copyfile(folder/"one.hip",target)
    case=(str(target),"/obj/upper","/obj/lower",1,1,"y",None,None,"")
    baseline=gap(*case);assert baseline["lowest"]["gap"]==1
    shutil.copyfile(folder/"three.hip",target)
    updated=gap(*case);assert updated["lowest"]["gap"]==3 and baseline["process_pid"]==updated["process_pid"]

    # Acquire a clean baseline, then deliberately install the custom HDA only in the warm process.
    protected=str(folder/"guarded.hip")
    with patch.dict(os.environ,{"HOUDINI_RESEARCH_WORKER":"spawn"}):
        trial=native("sweep", hip=protected, node="/obj/RAIN/Wave_1",control="height",values=[.018,.045],topic="water")
    assert trial["process"]=="fresh"
    marker=gap(*case);assert int((folder/"observed-pid.txt").read_text())==marker["process_pid"]
    replay=native("replay",key=trial["id"])
    assert replay["verified_geometry_replay"] and replay["process"]=="fresh" and replay["process_pid"]!=marker["process_pid"]
    learn(kind="node",status="reproduced",title="Test",summary="Fresh remeasurement",topics=["water"],sources=[trial["id"],replay["id"]])
    warm1=native("sweep",hip=protected,node="/obj/RAIN/Wave_1",control="height",values=[.018,.045],topic="water")
    warm2=native("sweep",hip=protected,node="/obj/RAIN/Wave_1",control="height",values=[.018,.045],topic="water")
    assert warm1["process"]==warm2["process"]=="warm"
    try:
        learn(kind="node",status="reproduced",title="No",summary="Warm only",topics=["water"],sources=[warm1["id"],warm2["id"]])
    except ValueError as exc:
        assert "fresh" in str(exc)
    else:
        raise AssertionError("Two warm sweeps promoted a node résumé")

    old=clone_record(trial["id"])
    witness=read(old);witness["baseline"]["version"]="20.5.000";write(old,witness);unchanged=old.read_bytes()
    replay=native("replay",key=trial["id"])
    assert replay["reuse_status"]=="conditions_changed" and replay["geometry_match"] and replay["parameters_match"]
    assert not replay["verified"] and old.read_bytes()==unchanged

    recipe=search(topic="fireworks",kind="recipe")["cards"][0]["id"]
    assert verify_recipe(recipe)["verified"]
    file=clone_record(recipe); src=read(file);src["state"]["version"]="20.5.000";write(file,src)
    changed=verify_recipe(recipe)
    assert changed["reuse_status"]=="conditions_changed" and changed["geometry_match"] and not changed["verified"]

    variant=native("variant",hip=protected,node="/obj/RAIN/ART_DIRECTION",changes={"amplitude":.82},
                   witness="/obj/RAIN/Reflected_sky_and_shore",topic="water",note="runtime test")
    assert native("restore",key=variant["id"])["verified"]
    file=clone_record(variant["id"]);src=read(file);src["version"]="20.5.000";write(file,src);unchanged=file.read_bytes()
    changed=native("restore",key=variant["id"])
    assert changed["reuse_status"]=="conditions_changed" and changed["geometry_match"] and file.read_bytes()==unchanged
    with patch.dict(os.environ,{"HOUDINI_RESEARCH_WORKER_IDLE":"0.25"}):
        gap(*query);pool.proc.wait(timeout=5)
        with patch.dict(os.environ,{"HOUDINI_RESEARCH_WORKER_TIMEOUT":"0.01"}):
            try:gap(*query)
            except TimeoutError:pass
            else:raise AssertionError("Expected a startup deadline")
        assert gap(*query)["status"]=="passed"
    print("PASS: three 76-frame gaps",times,"seconds; cold/warm PID",pids,
          "HDA isolation, changed HIP, independent replays, changed conditions, crash, idle and deadline recovery")


if __name__=="__main__":
    if "--fixture" in sys.argv:
        fixture(Path(sys.argv[-1]))
    else:
        import contextlib
        from unittest.mock import patch
        from hlab.worker_pool import pool
        with tempfile.TemporaryDirectory(prefix="houdini-runtime-test-") as directory:
            with patch.dict(os.environ,{"HOUDINI_RESEARCH_HOME":directory}), contextlib.ExitStack() as stack:
                stack.callback(pool.close)
                acceptance(Path(directory))
