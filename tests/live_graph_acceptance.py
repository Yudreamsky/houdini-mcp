"""Rebuild and measure the fireworks recipe through a real MCP client and a disposable Houdini UI."""
import asyncio
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from hlab.bridge import call_in
from hlab.storage import read, write

ROOT = "/obj/HoudiniResearch"
SOURCE, SCATTER, TRAILS = (ROOT + "/" + name for name in ("SOURCE", "SCATTER", "TRAILS"))
FRAMES = [24, 36, 48]
COUNTS = [32, 96, 192]
TRAIL_CONTROLS = ("speed", "drag", "gravity", "trail", "second_delay", "tint")

# These test-only probes are registered exclusively in the disposable process.
STARTUP = """
import os, sys, hou
sys.path.insert(0, os.environ["HOUDINI_RESEARCH_ROOT"])
from hlab import host, scene

def history():
    vp = scene.viewer().curViewport()
    cam = vp.camera()
    return dict(undo=hou.undos.undoLabels(), redo=hou.undos.redoLabels(), frame=hou.frame(),
                camera=cam.path() if cam else None, objects=[n.path() for n in hou.node("/obj").children()])

def view():
    vp = scene.viewer().curViewport()
    return dict(transform=vp.viewTransform().asTuple(), locked=vp.isCameraLockedToView())

scene.ACTIONS.update(qa_history=history, qa_view=view, qa_undo=hou.undos.performUndo, qa_redo=hou.undos.performRedo,
                     qa_free_camera=lambda:scene.viewer().curViewport().useDefaultCamera(),
                     qa_hotkeys=lambda:hou.hotkeys.resolveAssignments(("h",),("h.undo","h.redo")))
host.start()
"""


def build_network():
    return [
        dict(op="create", path=ROOT, type="geo"),
        dict(op="create", path=SOURCE, type="sphere"),
        dict(op="set", path=SOURCE, parm="type", value="polymesh"),
        dict(op="create", path=SCATTER, type="scatter::2.0"),
        dict(op="connect", path=SCATTER, source=SOURCE),
        dict(op="set", path=SCATTER, parm="forcetotal", value=1),
        dict(op="set", path=SCATTER, parm="npts", value=96),
        dict(op="set", path=SCATTER, parm="seed", value=17),
        dict(op="create", path=TRAILS, type="python", template="fireworks.trails"),
        dict(op="connect", path=TRAILS, source=SCATTER),
        dict(op="flags", path=TRAILS, display=True, render=True),
    ]


def signatures(samples):
    return [s["metrics"]["output_sha256"] for s in samples]


def network(rows):
    fields = ("type", "inputs", "parameters", "flags")
    return {r["relative"]: {k: r[k] for k in fields} for r in rows["nodes"]}


async def exercise(client, directory, session, report):
    def qa(name):
        return call_in(directory, "qa_" + name)

    async def invoke(tool, **args):
        result = await client.call_tool(tool, args)
        assert not result.isError, (tool, [s.text for s in result.content if s.type == "text"])
        payload = result.structuredContent
        if payload is None:
            payload = json.loads(next(s.text for s in result.content if s.type == "text"))
        return payload

    async def recipe(name, **args):
        return await invoke("domain_recipe", action="run", domain="fireworks", name=name, arguments=args)

    async def graph(tool, **args):
        return await invoke(tool, session_id=session["id"], **args)

    async def study(action, **args):
        return await graph("node_lab", scope="live", action=action, **args)

    async def reject(ops, contains):
        before = qa("history")
        result = await client.call_tool("graph_edit", {"ops": ops, "session_id": session["id"]})
        msg = " ".join(s.text for s in result.content if s.type == "text")
        assert result.isError and contains.lower() in msg.lower(), (ops, msg)
        assert before == qa("history"), (before, qa("history"))
        return msg

    assert session in (await invoke("window_session"))["windows"]
    types = await graph("node_types", query="scatter", category="Sop", limit=100)
    assert any(t["name"] == "scatter::2.0" for t in types["items"])
    before = qa("history")
    assert not before["objects"], before
    init = await recipe("session", initialize=True)
    assert init["pid"] == session["pid"] and init["path"] == ROOT
    reference = await graph("graph_read", path=ROOT)
    initial_cook = await graph("cook", node=TRAILS, frame=36)
    quota = await recipe("experiment", control="npts", samples=COUNTS, frame=36)
    old_sweep = (await invoke("knowledge", key=quota["id"]))["details"]["samples"]
    looks = await recipe("compare", frames=FRAMES)
    old_looks = (await invoke("knowledge", key=looks["id"]))["details"]["candidates"]
    assert len(set(signatures(old_sweep))) == len(COUNTS)
    assert old_looks["B"]["samples"][1]["metrics"]["output_sha256"] == init["metrics"]["output_sha256"]

    # Capture using a camera that is not currently bound; validate decoded pixels, playhead and camera restore.
    qa("free_camera")
    prior = qa("history")
    prior_view = qa("view")
    shot = await client.call_tool("capture", {"frame":43, "camera":"/obj/ResearchCamera", "session_id":session["id"]})
    assert not shot.isError, shot.content[0]
    info = json.loads(next(s.text for s in shot.content if s.type == "text"))
    image_bytes = base64.b64decode(next(s.data for s in shot.content if s.type == "image"), validate=True)
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        assert image.format == "PNG" and image.size == (704,396)
        assert any(b-a > 10 for a,b in image.convert("RGB").getextrema()), image.getextrema()
    original_png = directory/"images"/(info["image_id"]+".png")
    assert hashlib.sha256(original_png.read_bytes()).hexdigest() == info["sha256"]
    assert info["camera"] == "/obj/ResearchCamera" and info["frame"] == 43
    assert qa("history") == prior, (prior, qa("history"))
    restored_view = qa("view")
    assert prior_view["locked"] == restored_view["locked"]
    assert max(abs(a-b) for a,b in zip(prior_view["transform"], restored_view["transform"])) < 1e-6
    report["capture"] = {k: info[k] for k in ("sha256", "frame", "camera", "image_id")}

    qa("undo")
    assert qa("history")["objects"] == before["objects"]
    created = await graph("graph_edit", ops=build_network(), label="rebuild fireworks")
    assert created["count"] == len(build_network()) and all(not row["errors"] for row in created["steps"])
    assert qa("history")["undo"] == ["MCP: rebuild fireworks", *before["undo"]]
    rows = await graph("graph_read", path=ROOT, snapshot=True)
    rebuilt = network(rows)
    assert rebuilt == network(reference), {
        (name,field):(r[field], rebuilt.get(name, {}).get(field)) for name,r in network(reference).items()
        for field in r if r[field] != rebuilt.get(name, {}).get(field)
    }
    assert initial_cook == await graph("cook", node=TRAILS, frame=36)
    qa("undo")
    assert qa("history")["objects"] == before["objects"]
    qa("redo")
    assert network(await graph("graph_read", path=ROOT)) == rebuilt
    assert initial_cook == await graph("cook", node=TRAILS, frame=36)
    report["rebuild"] = {"steps":created["count"], "nodes":sorted(rebuilt), "points":initial_cook["points"],
                         "primitives":initial_cook["primitives"], "undo_redo":True}

    report["rejections"] = [
        await reject([dict(op="create", type="null", path=ROOT+"/TEMP"),
                      dict(op="create", type="null", path=ROOT+"/TEMP2"),
                      dict(op="connect", path=ROOT+"/TEMP2", source=ROOT+"/MISSING")], "Step 3 rolled back"),
        await reject([dict(op="set", path=TRAILS, parm="python", value="print('test only')")], "Code-capable"),
        await reject([dict(op="set", path=SCATTER, parm="npts", expect=321, value=42)], "Expectation"),
    ]
    assert not (await graph("diff", key=rows["snapshot"]))["changed"]
    assert network(await graph("graph_read", path=ROOT)) == rebuilt
    await graph("graph_edit", ops=[dict(op="set", path=SCATTER, parm="npts", expect=96, value=72)])
    delta = await graph("diff", key=rows["snapshot"])
    assert delta["total_added"] == delta["total_removed"] == 0 and delta["total_changed"] == 1, delta
    changed = delta["changed"][0]
    assert changed["relative"] == "SCATTER" and changed["parameters"]["npts"]["after"]["value"] == 72, delta
    qa("undo")
    delta = await graph("diff", key=rows["snapshot"])
    assert delta["total_changed"] == delta["total_removed"] == delta["total_added"] == 0, delta
    prior = qa("history")
    sweep = await study("sweep", node=SCATTER, witness=TRAILS, control="npts", values=COUNTS, frame=36)
    assert sweep["baseline_restored"] and signatures(sweep["samples"]) == signatures(old_sweep)
    controls = {k:{n:look["parameters"][n] for n in TRAIL_CONTROLS} for k,look in old_looks.items()}
    comparison = await study("compare", node=TRAILS, variants=controls, frames=FRAMES)
    assert comparison["baseline_restored"]
    for label, samples in comparison["candidates"].items():
        assert signatures(samples["samples"]) == signatures(old_looks[label]["samples"])
    motion = await study("motion", node=TRAILS, frames=FRAMES)
    assert motion["baseline_restored"] and signatures(motion["samples"]) == signatures(old_looks["B"]["samples"])
    assert prior == qa("history")
    assert network(await graph("graph_read", path=ROOT)) == rebuilt
    report["matching_sweep_hashes"] = signatures(sweep["samples"])
    report["matching_variant_hashes"] = {k:signatures(v["samples"]) for k,v in comparison["candidates"].items()}
    report["matching_motion_hashes"] = signatures(motion["samples"])
    report["native_hotkeys"] = qa("hotkeys")


async def check(executable):
    repo = Path(__file__).resolve().parents[1]
    (repo/".research").mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="graph-accept-", dir=repo/".research"))
    startup = directory/"plugin"/"python3.11libs"/"uiready.py"
    startup.parent.mkdir(parents=True)
    startup.write_text(STARTUP, encoding="utf8")
    env = dict(os.environ, HOUDINI_RESEARCH_ROOT=str(repo), HOUDINI_RESEARCH_HOME=str(directory),
               HOUDINI_EXE=str(executable), HOUDINI_RESEARCH_ALLOW_CODE="0",
               HOUDINI_PATH=str(startup.parents[1])+os.pathsep+(os.environ.get("HOUDINI_PATH") or "&"))
    with (directory/"houdini.log").open("w", encoding="utf8") as log:
        gui = subprocess.Popen([str(executable)], env=env, cwd=repo, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        report = {"pid":gui.pid}
        try:
            print("Disposable graph acceptance GUI", gui.pid, directory, flush=True)
            registry = directory/"bridge/session.json"
            deadline = time.monotonic()+100
            while not registry.exists() and time.monotonic()<deadline and gui.poll() is None:
                await asyncio.sleep(.1)
            session = read(registry)
            assert session["pid"] == gui.pid
            stdio = StdioServerParameters(command=sys.executable,args=[str(repo/"run_mcp.py")],env=env,cwd=repo)
            async with stdio_client(stdio) as (rd,wr), ClientSession(rd,wr) as client:
                await client.initialize()
                await exercise(client, directory, session, report)
            report["pass"] = True
        finally:
            write(directory/"acceptance.json", report)
            if gui.poll() is None:
                gui.terminate()
            gui.wait(timeout=15)
        print(json.dumps(report,ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(check(Path(sys.argv[1]).resolve(strict=True)))
