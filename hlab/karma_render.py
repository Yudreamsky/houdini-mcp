"""Render a Karma frame, or a range of frames in one husk run, from a loaded HIP without saving it. Imported
inside hython only."""
import os
import time
from contextlib import contextmanager

import hou

from hlab import karma_lighting
from hlab.karma_materials import convert, is_light, objects, pbr_fix, pbr_report, plan, round_edges, used
from hlab.karma_spec import (PARMS, developed, excerpt, frames_saved, lighting, look_settings, read_log,
                             read_sequence_log, resolution)

TEMPORARY = "HR_KARMA_PREVIEW"


def cameras():
    return [n for n in objects() if n.type().name() == "cam"]


def lights():
    return [n for n in objects() if is_light(n) and n.isObjectDisplayed()
            and (n.parm("light_enable") is None or n.evalParm("light_enable"))]


def whole(value):
    return int(value) if float(value).is_integer() else value


def materials():
    found, bare = used()
    kinds = {}
    for path, entry in sorted(found.items()):
        kinds.setdefault(entry["kind"], []).append(path)
    return {"by_kind": {k: v[:12] for k, v in kinds.items()}, "counts": {k: len(v) for k, v in kinds.items()},
            "unassigned_objects": bare[:12], "unassigned_count": len(bare)}


def notes(engine, mats, light_count, report=None, planned=False):
    """report: conversions done (or planned) for this engine; None when conversion is switched off."""
    rows = []
    if not light_count:
        rows.append("场景里没有开着的灯，Karma 会自动加一盏头灯；亮度和阴影不代表最终效果。"
                    "可用 changes 里的 lighting（day、overcast、night、studio）临时布光。")
    kinds = mats["by_kind"]
    if kinds.get("missing"):
        rows.append(f"有 {len(kinds['missing'])} 个材质路径找不到节点（如 {kinds['missing'][0]}），会按默认材质渲染。")
    if report is None:
        if kinds.get("shop"):
            rows.append(f"有 {len(kinds['shop'])} 个旧式 /shop 材质（如 {kinds['shop'][0]}），Karma 不读取，按默认材质渲染；"
                        "材质转换已关闭。")
        if engine == "xpu" and kinds.get("vex"):
            rows.append(f"有 {len(kinds['vex'])} 个 VEX 材质 XPU 不支持（如 {kinds['vex'][0]}）；要准确效果用 engine=cpu。")
    else:
        if report["converted"]:
            sources = "、".join(r["source"] for r in report["converted"][:4])
            rows.append(f"{'渲染时会' if planned else '已'}把 {len(report['converted'])} 个材质临时转成 MaterialX"
                        f"（{sources}），效果为近似，工程文件不变。")
        for row in report["unconverted"][:6]:
            rows.append(f"{row['source']}：{row['reason']}。")
    if engine == "xpu" and kinds.get("principled"):
        rows.append("XPU 以 USD Preview Surface 近似 Principled Shader；实测颜色、粗糙度、金属度、法线和发光贴图，"
                    "以及玻璃和清漆都正常；用到凹凸贴图、透明度贴图或镂空（不透明度贴图、底色贴图的透明通道）的会先转成 MaterialX。")
    return rows


def preview(engine):
    rows = plan(engine)
    return {"converted": [r for r in rows if r["action"] == "convert"],
            "unconverted": [r for r in rows if r["action"] != "convert"]}


def describe(rop):
    return {"path": rop.path(), "camera": rop.evalParm("camera"), "engine": rop.evalParm("engine"),
            "samples": rop.evalParm("pathtracedsamples"), "denoiser": rop.evalParm("denoiser"),
            "resolution": [rop.evalParm("resolutionx"), rop.evalParm("resolutiony")]}


def inspect(req):
    karma, other = [], []
    for rop in hou.node("/out").allSubChildren():
        if isinstance(rop, hou.RopNode):
            (karma.append(describe(rop)) if rop.type().name() == "karma"
             else other.append({"path": rop.path(), "type": rop.type().nameWithCategory()}))
    stage = hou.node("/stage")
    mats, lit = materials(), lights()
    conversion = {engine: preview(engine) for engine in ("xpu", "cpu")}
    warnings = notes("xpu", mats, len(lit), conversion["xpu"], planned=True)
    unreal = pbr_report()
    if unreal:
        first = unreal[0]
        warnings.append(f"有 {len(unreal)} 个材质的数值不符合真实材料（如 {first['material']}：{first['issues'][0]['reason']}）；"
                        "照片级出图前建议在工程里改，或渲染时加 pbr_fix=true 临时改正。")
    if not cameras():
        warnings.insert(0, "工程里没有 OBJ 相机，Karma 渲染需要一台相机。")
    if stage is not None and stage.children():
        warnings.append("发现 Solaris（/stage）节点；这一版只渲染 /obj 场景，Solaris 的渲染设置不会被读取。")
    return {"version": hou.applicationVersionString(), "frame": whole(hou.frame()), "fps": whole(hou.fps()),
            "frame_range": [whole(hou.hscriptExpression("$FSTART")), whole(hou.hscriptExpression("$FEND"))],
            "cameras": [{"path": c.path(), "resolution": [c.evalParm("resx"), c.evalParm("resy")]} for c in cameras()][:20],
            "lights": [{"path": n.path(), "type": n.type().name()} for n in lit][:20],
            "karma_rops": karma[:20], "other_rops": other[:20], "materials": mats,
            "material_conversion": conversion, "pbr": unreal[:20], "warnings": warnings}


def karma_rops():
    return [r for r in hou.node("/out").allSubChildren() if isinstance(r, hou.RopNode) and r.type().name() == "karma"]


def karma_rop(path, base=""):
    if path:
        rop = hou.node(path)
        if not isinstance(rop, hou.RopNode) or rop.type().name() != "karma":
            raise ValueError(f"Select a Karma ROP (Driver/karma) or leave rop empty: {path}")
        return rop, False
    if base == "scene":
        # The scene preset keeps a ROP's own settings, so it needs that ROP rather than a temporary one.
        found = karma_rops()
        if len(found) == 1:
            return found[0], False
        raise ValueError("Preset 'scene' keeps an existing Karma ROP's settings: " + (
            "pass rop= one of " + ", ".join(r.path() for r in found[:12]) if found
            else "this HIP has none, so use preview, standard or final"))
    return hou.node("/out").createNode("karma", TEMPORARY), True


def render_threads():
    configured = os.environ.get("HOUDINI_RESEARCH_RENDER_THREADS")
    # Leave a few logical cores for the desktop; the worker itself runs with HOUDINI_MAXTHREADS=8.
    return max(1, int(configured)) if configured else max(2, (os.cpu_count() or 8) - 4)


@contextmanager
def environment(values):
    """Set (or with None, remove) variables that husk inherits, then restore them."""
    previous = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def pick_camera(path, rop, temporary):
    path = path or ("" if temporary else rop.evalParm("camera"))
    found = cameras()
    if path:
        cam = hou.node(path)
        if not isinstance(cam, hou.ObjNode) or cam.type().name() != "cam":
            raise ValueError(f"Not an OBJ camera: {path}. Cameras: {', '.join(c.path() for c in found[:12]) or 'none'}")
        return cam
    if len(found) == 1:
        return found[0]
    if not found:
        raise ValueError("The scene has no OBJ camera")
    raise ValueError("Several cameras; choose one with camera=" + ", ".join(c.path() for c in found[:12]))


def fix_materials(chosen):
    """pbr_fix on the loaded copy. It runs before any conversion, so converted materials carry the corrected values."""
    return pbr_fix() if chosen.get("pbr_fix") else None


def round_shading(chosen):
    """Karma's rounded edges, after conversion: they attach to MaterialX surfaces."""
    if not chosen.get("round_edges"):
        return None
    return {"millimetres": chosen["round_edges"], **round_edges(chosen["round_edges"] / 1000.)}


def photoreal_notes(real):
    rows = []
    fixes = real.get("pbr_fixes")
    if fixes:
        rows.append(f"按真实材料临时改正了 {len(fixes)} 个材质（如 {fixes[0]['material']}：{'、'.join(fixes[0]['changes'])}），工程文件不变。")
    elif fixes == []:
        rows.append("材质数值都在真实范围内，pbr_fix 没有改动。")
    rounded = real.get("round_edges")
    if rounded:
        text = f"给 {len(rounded['materials'])} 个材质加了 {rounded['millimetres']:g} 毫米圆角（着色时混合法线，不改模型）"
        if rounded.get("skipped"):
            text += f"；{len(rounded['skipped'])} 个材质不是 MaterialX，没有圆角（如 {rounded['skipped'][0]}）"
        rows.append(text + "。")
    return rows


def apply_scene(scene):
    """Temporary edits to the loaded copy for this render: parameter overrides and hidden objects. Code-capable
    parameters follow graph_edit's rule and need the host opt-in. Returns what changed."""
    report = {"overrides": [], "hidden": []}
    if not scene:
        return report
    from hlab.live_graph import check_value, get_literal
    for path, value in scene.get("overrides", {}).items():
        parm = hou.parm(path)
        if parm is None:
            raise ValueError(f"overrides: no parameter {path}")
        check_value(parm, {"value": value, "replace_expression": True})
        template = parm.parmTemplate()
        takes_text = isinstance(template, hou.StringParmTemplate)
        if not isinstance(template, hou.MenuParmTemplate) and takes_text != isinstance(value, str):
            raise ValueError(f"overrides: cannot set {path} to {value!r}: it takes {'text' if takes_text else 'a number'}")
        animated, before = bool(parm.keyframes()), get_literal(parm)
        try:
            parm.deleteAllKeyframes()
            parm.set(value, follow_parm_reference=False)
        except (hou.Error, TypeError) as exc:
            raise ValueError(f"overrides: cannot set {path} to {value!r}: {exc}") from exc
        report["overrides"].append({"parm": path, "from": before, "to": get_literal(parm), "was_animated": animated})
    for path in scene.get("hide", []):
        node = hou.node(path)
        if not isinstance(node, hou.ObjNode):
            raise ValueError(f"hide: not an object: {path}")
        node.setDisplayFlag(False)
        report["hidden"].append(path)
    return report


def scene_notes(report):
    rows = []
    changed, hidden = report["overrides"], report["hidden"]
    if changed:
        first = changed[0]
        text = f"临时改了 {len(changed)} 个场景参数（如 {first['parm']}：{first['from']} → {first['to']}）"
        frozen = sum(1 for row in changed if row["was_animated"])
        if frozen:
            text += f"，其中 {frozen} 个原来有动画或表达式，这次渲染按固定值"
        rows.append(text + "，工程文件不变。")
    if hidden:
        rows.append(f"临时隐藏了 {len(hidden)} 个物体（如 {hidden[0]}），工程文件不变。")
    return rows


def render(req, folder):
    """One frame (req frame, or the HIP's own) as render.png, or with req frames = [first, last] the whole range as
    render.<frame>.png from a single husk run, so the scene is translated and the shaders compile once."""
    chosen = req["settings"]
    span = req.get("frames")
    if span:
        hou.setFrame(span[0])
    elif req.get("frame") is not None:
        hou.setFrame(req["frame"])
    frame = whole(hou.frame())
    last = whole(span[1]) if span else frame
    edits = apply_scene(req.get("scene"))
    rop, temporary = karma_rop(req.get("rop", ""), req.get("preset", ""))
    cam = pick_camera(req.get("camera", ""), rop, temporary)
    width, height = resolution((cam.evalParm("resx"), cam.evalParm("resy")), chosen)
    # With a tone curve, an exposure or exr, Karma writes linear EXR and develop() makes the PNG from it.
    kind = "exr" if developed(chosen) else "png"
    tone, stops = chosen.get("tone", "off"), chosen.get("exposure", 0.)
    picture, out, err = folder / f"render.{kind}", folder / "husk.log", folder / "husk.err"
    values = {"camera": cam.path(), "override_camerares": 0, "resolutionx": width, "resolutiony": height,
              "picture": str(folder / f"render.$F4.{kind}") if span else str(picture), "soho_foreground": 1,
              "verbosity": 5, "log": 1, "logappend": 0,
              "husk_stdout": str(out), "husk_stderr": str(err), "savetodirectory": str(folder / "usd")}
    if span:
        values.update(trange=1, allframesatonce=1)
    values.update({parm: chosen[name] for name, parm in PARMS.items() if name in chosen})
    if "samples" in chosen:
        # CPU Karma honours the path-traced sample count only in this mode; XPU always path traces.
        values["convergence_mode"] = "Path Traced"
    if "time_limit" in chosen:
        values.update(addtimelimit=1, timelimit=chosen["time_limit"], husk_timelimitperimage=1)
    engine = chosen.get("engine") or rop.evalParm("engine")
    if engine == "xpu":
        values["abortnogpudevice"] = 1
    for name, value in values.items():
        rop.parm(name).set(int(value) if isinstance(value, bool) else value)
    if span:
        for parm, value in zip(rop.parmTuple("f"), (frame, last, 1)):
            parm.deleteAllKeyframes()  # a new ROP's range is the expressions $FSTART and $FEND
            parm.set(value)
    fixes = fix_materials(chosen)
    report = convert(engine, force=bool(chosen.get("round_edges"))) if chosen.get("convert_materials", True) else None
    real = {"pbr_fixes": fixes, "round_edges": round_shading(chosen)}
    look = lighting(chosen)
    lit_by = karma_lighting.apply(look, cam, rop, folder) if look else None
    mats = materials()
    lit = [n for n in lights() if not lit_by or n.path() not in lit_by["turned_off"]]
    threads = render_threads()
    started = time.perf_counter()
    failure = None
    # Without the Embree switch, XPU's CPU device can finish small frames before the GPU contributes.
    with environment({"HOUDINI_MAXTHREADS": str(threads),
                      "KARMA_XPU_DISABLE_EMBREE_DEVICE": "1" if engine == "xpu" else None}):
        try:
            rop.render(frame_range=(frame, last))
        except hou.OperationFailed as exc:
            failure = str(exc)
    seconds = time.perf_counter() - started
    stdout = out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""
    stderr = err.read_text(encoding="utf-8", errors="replace") if err.is_file() else ""
    if span:
        info = read_sequence_log(stdout, stderr)
        saved = frames_saved([p.name for p in folder.glob(f"render.*.{kind}") if p.stat().st_size], frame, stderr, kind)
        if not saved:
            raise RuntimeError(f"Karma render failed: {excerpt(stdout, stderr) or failure or 'no image was written'}")
        # husk 20.5 can crash while exiting after time-limited frames, after it has saved them all. Frames missing
        # from the end mean it stopped early: the host keeps what was saved and continues from the first gap.
        stopped = None if len(saved) == last - frame + 1 else (
            excerpt(stdout, stderr) or failure or "husk stopped without an error message")[:600]
        if kind == "exr":
            from hlab.karma_grade import develop
            for row in saved:
                source = folder / row["file"]
                row["file"] = source.with_suffix(".png").name
                develop(source, folder / row["file"], tone, stops)
                if chosen.get("exr"):
                    row["exr"] = source.name
        outcome = {"frames": saved, "stopped": stopped,
                   "status": "time_limit" if any(row["status"] == "time_limit" for row in saved) else "completed"}
    else:
        info = read_log(stdout, stderr)
        # husk 20.5 can crash while exiting after a time-limited frame, after it has saved the image.
        if failure and not (info["time_limit_reached"] and picture.is_file()):
            raise RuntimeError(f"Karma render failed: {excerpt(stdout, stderr) or failure}")
        if not picture.is_file():
            raise RuntimeError("Karma finished without writing an image")
        outcome = {"file": picture.name, "status": "time_limit" if info["time_limit_reached"] else "completed"}
        if kind == "exr":
            from hlab.karma_grade import develop
            develop(picture, folder / "render.png", tone, stops)
            outcome["file"] = "render.png"
            if chosen.get("exr"):
                outcome["exr"] = picture.name
    effective = {name: rop.evalParm(parm) for name, parm in PARMS.items()}
    effective.update(motion_blur=bool(effective["motion_blur"]), depth_of_field=bool(effective["depth_of_field"]),
                     time_limit=rop.evalParm("timelimit") if rop.evalParm("addtimelimit") else None,
                     convert_materials=report is not None, round_edges=chosen.get("round_edges", 0.),
                     pbr_fix=bool(chosen.get("pbr_fix")), tone=tone, exposure=stops, exr=bool(chosen.get("exr")),
                     **look_settings(look))
    return {**outcome, "log": out.name, "frame": frame, "camera": cam.path(), "rop": rop.path(),
            "temporary_rop": temporary, "resolution": [width, height], "settings": effective,
            "seconds": round(seconds, 2),
            "render_threads": threads, "lights": len(lit), "materials": report, "lighting": lit_by, "photoreal": real,
            "scene": edits,
            "notes": scene_notes(edits) + (karma_lighting.notes(lit_by) if lit_by else []) + photoreal_notes(real)
            + notes(engine, mats, len(lit), report),
            **info}


def build_sample(path):
    hou.hipFile.clear(suppress_save_prompt=True)
    obj, mat = hou.node("/obj"), hou.node("/mat")
    red = mat.createNode("principledshader::2.0", "red_principled")
    red.parmTuple("basecolor").set((.8, .08, .06))
    green = mat.createNode("mtlxstandard_surface", "green_materialx")
    green.parmTuple("base_color").set((.1, .7, .2))

    def shape(name, sop, material, **parms):
        geo = obj.createNode("geo", name)
        node = geo.createNode(sop)
        for key, value in parms.items():
            (node.parmTuple(key) if isinstance(value, tuple) else node.parm(key)).set(value)
        node.setDisplayFlag(True)
        node.setRenderFlag(True)
        geo.parm("shop_materialpath").set(material)

    shape("BOX", "box", red.path(), t=(-.8, .5, 0))
    shape("BALL", "sphere", green.path(), type=2, freq=12, t=(.8, .5, 0), rad=(.5, .5, .5))
    shape("GROUND", "grid", "", size=(10, 10))
    key = obj.createNode("hlight::2.0", "KEY")
    key.parm("light_type").set("grid")
    key.parmTuple("areasize").set((3, 3))
    key.parmTuple("t").set((0, 4, 3))
    key.parmTuple("r").set((-55, 0, 0))
    key.parm("light_exposure").set(3)
    cam = obj.createNode("cam", "CAM")
    cam.parmTuple("t").set((0, 1.6, 5))
    cam.parmTuple("r").set((-10, 0, 0))
    cam.parm("resx").set(1280)
    cam.parm("resy").set(720)
    hou.setFrame(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    hou.hipFile.save(str(path), save_to_recent_files=False)
    return {"hip": str(path), "version": hou.applicationVersionString()}
