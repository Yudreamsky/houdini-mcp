"""Small set of operations on a purpose-built, visible research fixture."""
import hashlib
import math
import os
import time
from pathlib import Path

import hou

from .storage import details, home, ident, record, sha, stored, uid

PRESETS = {
    "A": dict(speed=4.6, drag=1.6, gravity=1.0, trail=.24, second_delay=0., tint=.28),
    "B": dict(speed=4.2, drag=1.15, gravity=2.9, trail=.65, second_delay=0., tint=.90),
    "C": dict(speed=4.4, drag=1.45, gravity=1.7, trail=.37, second_delay=.52, tint=.45),
}
BOUNDS = {"npts": (8, 500), "seed": (0, 10000), "relaxiterations": (0, 20),
          "burst_frame": (4, 50), "speed": (.1, 8.), "drag": (.1, 4.), "gravity": (0., 5.),
          "trail": (.03, 1.5), "second_delay": (0., 1.4), "tint": (0., 1.)}
INTEGERS = {"npts", "seed", "relaxiterations", "burst_frame"}
VERSION = "fireworks-curves/1"


def viewer():
    pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if pane is None:
        raise RuntimeError("Open a Scene Viewer in the research window")
    return pane


def lab():
    node = hou.node(getattr(hou.session, "hr_active_path", "/obj/HoudiniResearch"))
    if node is None or node.userData("research_fixture") != VERSION:
        raise RuntimeError("Initialize the research fixture first")
    return node


def focus(node):
    node.setCurrent(True, clear_all_selected=True)
    net = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if net:
        net.setPwd(node.parent())
        net.setCurrentNode(node)
        x, y = node.position()
        net.setVisibleBounds(hou.BoundingRect(x-5, y-3, x+6, y+5))


def initialize():
    if getattr(hou.session, "hr_active_path", None):
        return state()
    obj = hou.node("/obj")
    if obj.children():
        raise RuntimeError("Initialize only in an empty dedicated research scene")
    geo = obj.createNode("geo", "HoudiniResearch", run_init_scripts=False)
    cam = None
    try:
        src = geo.createNode("sphere", "SOURCE")
        src.parm("type").set("polymesh")
        scatter = geo.createNode("scatter::2.0", "SCATTER", exact_type_name=True)
        scatter.setInput(0, src)
        scatter.parm("forcetotal").set(1)
        scatter.parm("npts").set(96)
        scatter.parm("seed").set(17)
        trails = geo.createNode("python", "TRAILS")
        trails.setInput(0, scatter)
        group = trails.parmTemplateGroup()
        for key in ("burst_frame", *PRESETS["B"], "tick"):
            initial = 18 if key == "burst_frame" else PRESETS["B"].get(key, 1.)
            cls = hou.IntParmTemplate if key == "burst_frame" else hou.FloatParmTemplate
            template = cls(key, key.replace("_", " ").title(), 1, default_value=(initial,), min=BOUNDS.get(key, (1,96))[0], max=BOUNDS.get(key, (1,96))[1])
            if key == "tick":
                template.hide(True)
            group.append(template)
        trails.setParmTemplateGroup(group)
        trails.parm("tick").setExpression("$FF", hou.exprLanguage.Hscript)
        trails.parm("python").set(Path(__file__).with_name("firework_sop.py").read_text(encoding="utf-8"))
        trails.setDisplayFlag(True)
        trails.setRenderFlag(True)
        geo.layoutChildren()
        cam = obj.createNode("cam", "ResearchCamera")
        cam.parmTuple("t").set((0, -.65, 17))
        cam.parm("focal").set(38)
        cam.setDisplayFlag(False)
        scene_view = viewer()
        scene_view.constructionPlane().setIsVisible(False)
        viewport = scene_view.curViewport()
        viewport.setCamera(cam)
        for guide in (hou.viewportGuide.XZPlane, hou.viewportGuide.OriginGnomon, hou.viewportGuide.FloatingGnomon):
            viewport.settings().enableGuide(guide, False)
        hou.setFps(24)
        hou.playbar.setFrameRange(1, 84)
        hou.playbar.setPlaybackRange(1, 84)
        hou.setFrame(36)
        geo.setUserData("research_fixture", VERSION)
        hou.session.hr_active_path = geo.path()
        focus(trails)
        return state()
    except Exception:
        geo.destroy()
        if cam:
            cam.destroy()
        hou.session.hr_active_path = None
        raise


def parameter(key):
    if key not in BOUNDS:
        raise ValueError("Unsupported research control: " + key)
    return lab().node("SCATTER" if key in ("npts","seed","relaxiterations") else "TRAILS").parm(key)


def values():
    return {key: parameter(key).eval() for key in BOUNDS}


def validated(changes):
    for key, value in changes.items():
        parm = parameter(key)
        lo, hi = BOUNDS[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be numeric in [{lo}, {hi}]")
        if key in INTEGERS and int(value) != value:
            raise ValueError(f"{key} requires an integer")
        if parm.isLocked() or parm.keyframes() or parm.getReferencedParm() != parm or parm.isDisabled():
            raise ValueError(f"{key} is animated, linked, disabled or locked")
    return {key: int(v) if key in INTEGERS else float(v) for key, v in changes.items()}


def apply(changes):
    changes = validated(changes)
    previous = {key: parameter(key).eval() for key in changes}
    try:
        for key, value in changes.items():
            parameter(key).set(value)
        return metrics()
    except Exception:
        for key, value in previous.items():
            parameter(key).set(value)
        raise


def metrics():
    geo = lab()
    source = geo.node("SCATTER").geometry()
    trails = geo.node("TRAILS")
    rendered = trails.geometry()
    if not rendered or trails.errors() or not rendered.intrinsicValue("pointcount"):
        raise RuntimeError(str(trails.errors()) or "Empty trails output")
    geometry_hash = hashlib.sha256(rendered.pointFloatAttribValuesAsString("P") + rendered.pointFloatAttribValuesAsString("Cd")).hexdigest()
    return dict(scatter_points=source.intrinsicValue("pointcount"), output_primitives=rendered.intrinsicValue("primitivecount"),
                scatter_sha256=hashlib.sha256(source.pointFloatAttribValuesAsString("P")).hexdigest(),
                output_sha256=geometry_hash)


def state():
    g = lab()
    return dict(path=g.path(), version=hou.applicationVersionString(), fixture=VERSION, pid=os.getpid(),
                frame=hou.frame(), node_type=g.node("SCATTER").type().nameWithCategory(), parameters=values(), metrics=metrics())


def set_controls(preset="", changes=None):
    if preset and preset not in PRESETS:
        raise ValueError("Choose A, B or C")
    apply({**PRESETS.get(preset, {}), **(changes or {})})
    focus(lab().node("TRAILS"))
    return state()


def capture(frame):
    if type(frame) is not int or not 1 <= frame <= 84:
        raise ValueError("frame must be 1..84")
    lab()
    hou.setFrame(frame)
    v = viewer()
    view = v.curViewport()
    settings = v.flipbookSettings().stash()
    folder = home() / "images"
    folder.mkdir(parents=True, exist_ok=True)
    key = uid()
    path = folder / (key + ".png")
    settings.output(str(path).replace("\\", "/"))
    settings.outputToMPlay(False)
    settings.beautyPassOnly(True)
    settings.frameRange((frame, frame))
    settings.useResolution(True)
    settings.resolution((704, 396))
    settings.cropOutMaskOverlay(True)
    v.flipbook(view, settings)
    for _ in range(40):
        if path.exists() and path.stat().st_size:
            break
        time.sleep(.05)
    if not path.is_file() or not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Viewport did not produce a PNG")
    camera = view.camera()
    return {"image_id": key, "sha256": sha(path), "frame": frame, "camera": camera.path() if camera else "free viewport",
            "view_transform": list(view.viewTransform().asTuple()), "metrics":metrics()}


def sweep(control, samples, frame=36):
    if not 2 <= len(samples) <= 7 or len(set(samples)) != len(samples):
        raise ValueError("Choose 2..7 distinct values")
    for value in samples:
        validated({control:value})
    base = state()
    results = []
    try:
        for value in samples:
            apply({control:value})
            result = capture(frame)
            result["actual"] = parameter(control).eval()
            results.append(result)
    finally:
        parameter(control).set(base["parameters"][control])
        hou.setFrame(base["frame"])
    restored = state()
    if base["parameters"] != restored["parameters"] or base["metrics"] != restored["metrics"]:
        raise RuntimeError("Baseline restoration mismatch")
    category = "scatter" if control in ("npts","seed","relaxiterations") else "fireworks"
    title = f"{base['node_type'] if category == 'scatter' else 'TRAILS'} / {control}"
    points = [s["metrics"]["scatter_points"] for s in results]
    summary = f"Frame {frame}, tested {samples}, scatter point counts {points}."
    card = record("experiment", title, [category,"particles","fireworks"], summary,
                  {"baseline":base, "control":control, "samples":results, "baseline_restored":True})
    if len({s["metrics"]["output_sha256"] for s in results}) == 1:
        gap = record("gap", "No observed output difference: " + control, [category,"fireworks"],
                     f"Frame {frame} has identical geometry and color. Check activation conditions or sample another frame.",
                     {"sources":[card["id"]]}, status="open")
        card["gap"] = gap["id"]
    return card


def compare(frames):
    if not 1 <= len(frames) <= 4 or any(type(f) is not int or not 1 <= f <= 84 for f in frames):
        raise ValueError("Choose 1..4 frame numbers in 1..84")
    base = state()
    candidates = {}
    try:
        for key, changes in PRESETS.items():
            apply(changes)
            candidates[key] = {"parameters":values(), "samples":[capture(f) for f in frames]}
    finally:
        apply({key:base["parameters"][key] for key in PRESETS["B"]})
        hou.setFrame(base["frame"])
    if state()["metrics"] != base["metrics"]:
        raise RuntimeError("Comparison baseline did not replay")
    return record("comparison", "Fireworks A/B/C", ["fireworks","particles"], f"Same camera and frames {frames}.",
                  {"baseline":base, "candidates":candidates})


def motion(start,end):
    if type(start) is not int or type(end) is not int or not (1 <= start < end <= 84 and end-start < 48):
        raise ValueError("Choose 2..48 consecutive frames in 1..84")
    previous = hou.frame()
    try:
        return {"fps":hou.fps(),"samples":[capture(f) for f in range(start,end+1)]}
    finally:
        hou.setFrame(previous)


def checkpoint(title, reason, parent=None, origin="baseline"):
    if parent:
        prior = details(parent)
        if prior["kind"] != "recipe":
            raise ValueError("Parent must be a recipe")
    base = state()
    asset = uid()
    bundle = home() / "bundles" / (asset + ".cpio")
    bundle.parent.mkdir(parents=True, exist_ok=True)
    node = lab()
    node.parent().saveItemsToFile((node,), str(bundle))
    try:
        return record("recipe", title, ["particles","fireworks"], reason,
                      {"state":base,"bundle":asset,"sha256":sha(bundle)}, parent, origin)
    except Exception:
        bundle.unlink(missing_ok=True)
        raise


def replay(key):
    row = details(key)
    if row["kind"] != "recipe":
        raise ValueError("Select a recipe")
    info = row["details"]
    prev = lab()
    bundle = stored("bundles",ident(info["bundle"]) + ".cpio")
    if sha(bundle) != info["sha256"]:
        raise ValueError("Checkpoint content changed")
    saved = info["state"]
    if saved["version"] != hou.applicationVersionString():
        raise ValueError("Checkpoint requires its recorded Houdini version")
    obj = hou.node("/obj")
    before = set(obj.children())
    prev_frame = hou.frame()
    was_visible = prev.isDisplayFlagSet()
    try:
        obj.loadItemsFromFile(str(bundle))
        added = set(obj.children()) - before
        if len(added) != 1:
            raise ValueError("Unexpected checkpoint structure")
        new = added.pop()
        hou.session.hr_active_path = new.path()
        hou.setFrame(saved["frame"])
        now = state()
        if now["parameters"] != saved["parameters"] or now["metrics"] != saved["metrics"]:
            raise ValueError("Checkpoint geometry or parameters differ on replay")
        new.setDisplayFlag(True)
        focus(new.node("TRAILS"))
        prev.setDisplayFlag(False)
        reuse = record("reuse", "Replay: " + row["title"], row["topics"],
                       "Same Houdini version, controls and frame geometry verified.",
                       {"sources":[key],"frame":now["frame"],"metrics":now["metrics"]}, key, "reproduced")
        return {"recipe":key, "verified":True, "state":now,"reuse_id":reuse["id"]}
    except Exception:
        hou.session.hr_active_path = prev.path()
        prev.setDisplayFlag(was_visible)
        hou.setFrame(prev_frame)
        for node in set(obj.children()) - before:
            node.destroy()
        raise


ACTIONS = {"initialize":initialize, "state":state, "set_controls":set_controls, "capture":capture,
           "sweep":sweep, "compare":compare, "motion":motion, "checkpoint":checkpoint, "replay":replay}
