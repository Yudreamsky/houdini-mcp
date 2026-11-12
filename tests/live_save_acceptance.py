"""Build a scene in a fresh managed window through a real MCP client, save it and render the saved HIP.

python -m tests.live_save_acceptance <houdini.exe>
Checks a camera's lens set in its creating batch (orthographic and perspective captures), a geo object's vm_
parameters, a 20 KB VEX snippet's short result, window_session(save) and a Karma render of the saved file.
"""
import ast
import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from hlab.runtime import discover
from hlab.storage import write
from hlab.window import registered

REPO = Path(__file__).resolve().parents[1]
CAM, GEO, TARGET, CODE = "/obj/CAMTEST", "/obj/GEOTEST", "/obj/TARGET", "/obj/CODE"
LENS = dict(resx=900, resy=2000, focal=110, projection=1, orthowidth=150)
APERTURE = 41.4214  # the camera's default horizontal aperture
# Two 30-unit red boxes (x, z) seen from z=500, left to right.
BOXES = {"NEAR": (-40, 0), "FAR": (40, -300)}


def expected_widths(projection):
    """Each box's width as a fraction of the frame width, from its corners."""
    widths = []
    for x, z in BOXES.values():
        xs = [(x + dx) / LENS["orthowidth"] if projection else (x + dx) / (500 - z - dz) * LENS["focal"] / APERTURE
              for dx in (-15, 15) for dz in (-15, 15)]
        widths.append(max(xs) - min(xs))
    return widths


def assert_widths(runs, width, projection):
    measured = [w / width for _, w in runs]
    expected = expected_widths(projection)
    assert len(runs) == 2 and all(abs(m - e) < .006 for m, e in zip(measured, expected)), (runs, measured, expected)
    return [round(m, 4) for m in measured], [round(e, 4) for e in expected]


FRESH = r"""
import json, sys, hou
hou.hipFile.load(sys.argv[1], suppress_save_prompt=True, ignore_load_warnings=True)
cam, geo = hou.node(sys.argv[2]), hou.node(sys.argv[3])
bare = {p.name() for p in hou.node("/obj").createNode("geo", run_init_scripts=False).parms()}
print(json.dumps({"lens": {k: cam.evalParm(k) for k in ("resx", "resy", "focal", "projection", "orthowidth")},
                  "vm": sorted(p.name() for p in geo.parms() if p.name().startswith("vm_") and p.name() not in bare),
                  "points": {p: hou.node(p).geometry().intrinsicValue("pointcount") for p in sys.argv[4:]}}))
"""


def snippet(rows):
    head = ("function float[] heights() { return array(0.0, 4.0); }\n"
            "float hs[] = heights();\n"
            "foreach (float h; hs) addpoint(0, set(100.0, h, 0.0));\n")
    lines = "".join(f"addpoint(0, set({100 + .3 * i:.1f}, -8.0, 0.0));  // padding so the snippet passes 20 KB\n"
                    for i in range(rows))
    return head + lines


def is_red(r, g, b, a):
    # Viewport red is about (170, 0, 0); Karma's lit red about (212, 115, 115). Half-covered edges count.
    return a > 127 and r > 60 and r > 1.4 * g and r > 1.4 * b


def red_runs(path):
    """Column runs of red pixels and the image size."""
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    columns = [any(is_red(*px[x, y]) for y in range(h)) for x in range(w)]
    runs, start = [], None
    for x, red in enumerate(columns + [False]):
        if red and start is None:
            start = x
        elif not red and start is not None:
            runs.append((start, x - start))
            start = None
    return runs, (w, h)


def red_height(path, start, width):
    """Rows that show red within one column run."""
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
    px = rgba.load()
    return sum(any(is_red(*px[x, y]) for x in range(start, start + width)) for y in range(rgba.height))


def fresh_check(hip, houdini, *paths):
    out = subprocess.run([str(discover(houdini).hython), "-c", FRESH, str(hip), CAM, GEO, *paths],
                         capture_output=True, text=True, timeout=300, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


async def exercise(client, home, hip, window, houdini, report):
    async def invoke(tool, **args):
        result = await client.call_tool(tool, args)
        text = next(s.text for s in result.content if s.type == "text")
        assert not result.isError, (tool, text)
        return result.structuredContent if result.structuredContent is not None else json.loads(text), len(text)

    async def graph(tool, **args):
        return (await invoke(tool, session_id=window["id"], **args))[0]

    folder = next(d for d, s in registered(home) if s["id"] == window["id"])

    async def capture(projection):
        result = await client.call_tool("capture", {"frame": 1, "camera": CAM, "session_id": window["id"]})
        assert not result.isError, result.content[0]
        info = json.loads(next(s.text for s in result.content if s.type == "text"))
        assert info["camera"] == CAM, info
        # The capture spans the camera frame across its width, in the camera's own proportions: 900 x 2000 fits
        # inside 704 x 396 as 178 x 396, and each 30-unit cube shows a square face.
        picture = folder / "images" / (info["image_id"] + ".png")
        runs, size = red_runs(picture)
        assert list(size) == info["resolution"] == [178, 396], (size, info)
        measured, expected = assert_widths(runs, size[0], projection)
        heights = [red_height(picture, start, width) for start, width in runs]
        if projection:  # in perspective a cube off the axis also shows a side face
            assert all(abs(h - w) <= 2 for h, (_, w) in zip(heights, runs)), (heights, runs)
        return {"image_id": info["image_id"], "size": size, "widths": measured, "expected": expected, "heights": heights}

    windows = (await invoke("window_session"))[0]["windows"]
    assert [w["id"] for w in windows] == [window["id"]], windows
    state = await graph("window_session", action="state")
    assert Path(state["hip"]) == hip and not state["unsaved"], state

    # The lens batch from the gap report, then a geo object's render properties in their creating batch.
    lens = await graph("graph_edit", label="lens camera", verbose=True, ops=[
        dict(op="create", path=CAM, type="cam"), *[dict(op="set", path=CAM, parm=k, value=v) for k, v in LENS.items()]])
    assert lens["steps"][0]["init_scripts"] is True, lens["steps"][0]
    assert [s["value"] for s in lens["steps"][1:]] == list(LENS.values()), lens["steps"]
    props = await graph("graph_edit", label="render properties", verbose=True, ops=[
        dict(op="create", path=GEO, type="geo"), dict(op="set", path=GEO, parm="vm_rendersubd", value=True)])
    assert props["steps"][0]["init_scripts"] is True and props["steps"][1]["value"] == 1, props["steps"]
    ops = [dict(op="set", path=CAM, parm="tz", value=500), dict(op="create", path=TARGET, type="geo"),
           dict(op="create", path=TARGET + "/MERGE", type="merge")]
    for i, (name, (x, z)) in enumerate(BOXES.items()):
        box = f"{TARGET}/{name}"
        ops += [dict(op="create", path=box, type="box"),
                *[dict(op="set", path=box, parm=p, value=30) for p in ("sizex", "sizey", "sizez")],
                dict(op="set", path=box, parm="tx", value=x), dict(op="set", path=box, parm="tz", value=z),
                dict(op="connect", path=TARGET + "/MERGE", source=box, input=i)]
    ops += [dict(op="create", path=TARGET + "/OUT", type="color"), dict(op="connect", path=TARGET + "/OUT", source=TARGET + "/MERGE"),
            dict(op="set", path=TARGET + "/OUT", parm="colorg", value=0), dict(op="set", path=TARGET + "/OUT", parm="colorb", value=0),
            dict(op="flags", path=TARGET + "/OUT", display=True, render=True)]
    await graph("graph_edit", label="depth targets", ops=ops)

    # Orthographic: both boxes are 30/150 of the frame. Perspective at 110 mm: the far box is smaller.
    report["capture"] = {"orthographic": await capture(1)}
    await graph("graph_edit", label="perspective", ops=[dict(op="set", path=CAM, parm="projection", value=0, expect=1)])
    report["capture"]["perspective"] = await capture(0)
    await graph("graph_edit", label="orthographic", ops=[dict(op="set", path=CAM, parm="projection", value=1, expect=0)])

    # A 20 KB snippet comes back short, with the sha256 of the text sent.
    rows = 270
    code = snippet(rows)
    assert 20000 < len(code) < 22000, len(code)
    edit, chars = await invoke("graph_edit", session_id=window["id"], label="long snippet", ops=[
        dict(op="create", path=CODE, type="geo"), dict(op="create", path=CODE + "/points", type="attribwrangle"),
        dict(op="set", path=CODE + "/points", parm="class", value=0),
        dict(op="set", path=CODE + "/points", parm="snippet", value=code),
        dict(op="flags", path=CODE + "/points", display=True, render=True)])
    # Of the five steps only the long text says something the request did not, so it alone is listed.
    assert (edit["count"], edit["omitted"], [s["step"] for s in edit["steps"]]) == (5, 4, [4]), edit
    value = edit["steps"][0]["value"]
    assert value == {"preview": code[:120], "length": len(code), "sha256": hashlib.sha256(code.encode()).hexdigest()}, value
    assert chars < 2048, chars
    report["long_snippet"] = {"characters_sent": len(code), "result_characters": chars, "sha256": value["sha256"]}

    cooked = {path: (await graph("cook", node=path, frame=1))["points"] for path in (TARGET + "/OUT", CODE + "/points")}
    assert cooked == {TARGET + "/OUT": 16, CODE + "/points": rows + 2}, cooked

    # A second placement is one copy step with its values; a clean batch returns totals only.
    twin = TARGET + "_TWIN"
    copied = await graph("graph_edit", label="second placement", ops=[
        dict(op="copy", source=TARGET, path=twin, set={"tx": 40, "ry": 90})])
    assert copied == {"label": "MCP: second placement", "count": 1, "ops": {"copy": 1}, "omitted": 1, "steps": []}, copied
    assert (await graph("cook", node=twin + "/OUT", frame=1))["points"] == 16
    placed = (await graph("graph_read", path="/obj", depth=1, limit=50))["nodes"]
    assert next(n for n in placed if n["path"] == twin)["parameters"]["tx"]["value"] == 40, placed
    await graph("graph_edit", label="remove the twin", ops=[dict(op="delete", path=twin)])
    report["copy"] = {"steps": copied["count"], "listed": len(copied["steps"])}

    # Save in place, render the saved file and read it back in a fresh hython.
    assert (await graph("window_session", action="state"))["unsaved"]
    saved = await graph("window_session", action="save")
    assert saved["status"] == "saved" and Path(saved["hip"]) == hip and saved["unsaved"] is False, saved
    assert saved["bytes"] == hip.stat().st_size and saved["sha256"] == hashlib.sha256(hip.read_bytes()).hexdigest()
    assert (await graph("window_session", action="state"))["unsaved"] is False
    render, _ = await invoke("karma", action="render", hip=str(hip), camera=CAM, preset="preview")
    assert render["status"] == "completed" and render["hip_unchanged"] and render["camera"] == CAM, render
    karma_runs, karma_size = red_runs(Path(render["path"]))
    karma_widths = assert_widths(karma_runs, karma_size[0], 1)[0]
    fresh = fresh_check(hip, houdini, *cooked)
    assert fresh["points"] == cooked, (fresh, cooked)
    assert fresh["lens"] == LENS and "vm_rendersubd" in fresh["vm"], fresh
    report["save"] = {**{k: saved[k] for k in ("hip", "bytes", "sha256", "unsaved")}, "cooked_points": cooked,
                      "fresh_hython": fresh | {"vm": len(fresh["vm"])}}
    report["karma"] = {k: render[k] for k in ("status", "seconds", "resolution", "camera", "path", "summary")}
    report["karma"].update(size=karma_size, widths=karma_widths)

    # Save as a new file, then refuse to write over the first one.
    first = hip.read_bytes()
    copy = hip.with_name("copy.hip")
    await graph("graph_edit", label="after save", ops=[dict(op="create", path="/obj/AFTER", type="null")])
    moved = await graph("window_session", action="save", hip=str(copy))
    assert Path(moved["hip"]) == copy and not moved["unsaved"] and hip.read_bytes() == first, moved
    refused = await client.call_tool("window_session", {"action": "save", "session_id": window["id"], "hip": str(hip)})
    message = " ".join(s.text for s in refused.content if s.type == "text")
    assert refused.isError and "Another file exists" in message and hip.read_bytes() == first, message
    report["save_as"] = {"hip": moved["hip"], "refused_overwrite": message[-160:]}

    # One line of the long snippet changes without resending it.
    before = len(code)
    patched, chars = await invoke("graph_edit", session_id=window["id"], label="one line", ops=[
        dict(op="patch", path=CODE + "/points", parm="snippet", find="array(0.0, 4.0)", replace="array(0.0, 5.0)")])
    assert patched == {"label": "MCP: one line", "count": 1, "ops": {"patch": 1}, "omitted": 1, "steps": []}, patched
    stored = await graph("graph_read", path=CODE, depth=1, limit=5)
    snippet_now = next(n for n in stored["nodes"] if n["path"] == CODE + "/points")["parameters"]["snippet"]["value"]
    assert "array(0.0, 5.0)" in snippet_now["preview"] and snippet_now["length"] == before, snippet_now
    assert snippet_now["sha256"] == hashlib.sha256(code.replace("4.0); }", "5.0); }").encode()).hexdigest(), snippet_now
    assert (await graph("cook", node=CODE + "/points", frame=1))["points"] == rows + 2
    report["patch"] = {"result_characters": chars, "snippet_characters": snippet_now["length"]}

    # A metal has nothing to reflect in the viewport and comes out dark; look="clay" shows its shape for that
    # capture only, and the next plain capture is the scene's own look again.
    await graph("graph_edit", label="metal block", ops=[
        dict(op="create", path="/mat/steel", type="principledshader::2.0"),
        dict(op="set", path="/mat/steel", parm="metallic", value=1),
        *[dict(op="set", path="/mat/steel", parm="basecolor" + c, value=0.8) for c in "rgb"],
        dict(op="create", path="/obj/METAL", type="geo"), dict(op="create", path="/obj/METAL/box", type="box"),
        *[dict(op="set", path="/obj/METAL/box", parm=p, value=120) for p in ("sizex", "sizey", "sizez")],
        dict(op="set", path="/obj/METAL", parm="shop_materialpath", value="/mat/steel"),
        dict(op="flags", path=TARGET, display=False), dict(op="flags", path=CODE, display=False)])

    async def grey(look):
        args = {"frame": 1, "camera": CAM, "session_id": window["id"]} | ({"look": look} if look else {})
        result = await client.call_tool("capture", args)
        assert not result.isError, result.content[0]
        info = json.loads(next(s.text for s in result.content if s.type == "text"))
        picture = Image.open(folder / "images" / (info["image_id"] + ".png")).convert("L")
        w, h = picture.size
        middle = list(picture.crop((w // 2 - 15, h // 2 - 15, w // 2 + 15, h // 2 + 15)).getdata())
        return sum(middle) / len(middle), info

    plain, plain_info = await grey("")
    matte, matte_info = await grey("clay")
    again, _ = await grey("")
    assert matte_info["look"] == "clay" and "look" not in plain_info, (matte_info, plain_info)
    assert matte > 90 and matte > plain + 40 and abs(again - plain) < 4, (plain, matte, again)
    report["clay"] = {"metal_grey": round(plain, 1), "clay_grey": round(matte, 1), "metal_again": round(again, 1)}


async def check(houdini):
    (REPO / ".research").mkdir(exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="save-accept-", dir=REPO / ".research")).resolve()
    hip = home / "start.hip"
    subprocess.run([str(discover(houdini).hython), "-c", "import sys, hou; hou.hipFile.save(sys.argv[1])", str(hip)],
                   check=True, capture_output=True, timeout=300)
    env = dict(os.environ, HOUDINI_RESEARCH_HOME=str(home), HOUDINI_EXE=str(houdini), HOUDINI_RESEARCH_ALLOW_CODE="0")
    launched = subprocess.run([sys.executable, str(REPO / "launch.py"), "--home", str(home), "--hip", str(hip),
                               "--new-window", "--houdini", str(houdini)],
                              env=env, cwd=REPO, capture_output=True, text=True, timeout=180, check=True)
    window = ast.literal_eval(launched.stdout.strip().splitlines()[-1])
    report = {"home": str(home), "window": window}
    print("Fresh managed window", window["pid"], home, flush=True)
    try:
        stdio = StdioServerParameters(command=sys.executable, args=[str(REPO / "run_mcp.py")], env=env, cwd=REPO)
        async with stdio_client(stdio) as (rd, wr), ClientSession(rd, wr) as client:
            await client.initialize()
            await exercise(client, home, hip, window, houdini, report)
        report["pass"] = True
    finally:
        write(home / "acceptance.json", report)
        os.kill(window["pid"], signal.SIGTERM)
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(check(Path(sys.argv[1]).resolve(strict=True)))
