"""Render one Karma frame from a loaded HIP without saving it. Imported inside hython only."""
import os
import time

import hou

from hlab.karma_materials import convert, is_light, objects, plan, used
from hlab.karma_spec import PARMS, excerpt, read_log, resolution

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
        rows.append("场景里没有开着的灯，Karma 会自动加一盏头灯；亮度和阴影不代表最终效果。")
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
        rows.append("XPU 以 USD Preview Surface 近似 Principled Shader；实测玻璃、金属、发光和点颜色正常，带贴图的会先转成 MaterialX。")
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
    if not cameras():
        warnings.insert(0, "工程里没有 OBJ 相机，Karma 渲染需要一台相机。")
    if stage is not None and stage.children():
        warnings.append("发现 Solaris（/stage）节点；这一版只渲染 /obj 场景，Solaris 的渲染设置不会被读取。")
    return {"version": hou.applicationVersionString(), "frame": whole(hou.frame()), "fps": whole(hou.fps()),
            "frame_range": [whole(hou.hscriptExpression("$FSTART")), whole(hou.hscriptExpression("$FEND"))],
            "cameras": [{"path": c.path(), "resolution": [c.evalParm("resx"), c.evalParm("resy")]} for c in cameras()][:20],
            "lights": [{"path": n.path(), "type": n.type().name()} for n in lit][:20],
            "karma_rops": karma[:20], "other_rops": other[:20], "materials": mats,
            "material_conversion": conversion, "warnings": warnings}


def karma_rop(path):
    if path:
        rop = hou.node(path)
        if not isinstance(rop, hou.RopNode) or rop.type().name() != "karma":
            raise ValueError(f"Select a Karma ROP (Driver/karma) or leave rop empty: {path}")
        return rop, False
    return hou.node("/out").createNode("karma", TEMPORARY), True


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


def render(req, folder):
    chosen = req["settings"]
    if req.get("frame") is not None:
        hou.setFrame(req["frame"])
    frame = whole(hou.frame())
    rop, temporary = karma_rop(req.get("rop", ""))
    cam = pick_camera(req.get("camera", ""), rop, temporary)
    width, height = resolution((cam.evalParm("resx"), cam.evalParm("resy")), chosen)
    picture, out, err = folder / "render.png", folder / "husk.log", folder / "husk.err"
    values = {"camera": cam.path(), "override_camerares": 0, "resolutionx": width, "resolutiony": height,
              "picture": str(picture), "soho_foreground": 1, "verbosity": 5, "log": 1, "logappend": 0,
              "husk_stdout": str(out), "husk_stderr": str(err), "savetodirectory": str(folder / "usd")}
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
    report = convert(engine) if chosen.get("convert_materials", True) else None
    mats, lit = materials(), lights()
    # Without this, XPU's CPU device can finish small frames before the GPU contributes.
    previous = os.environ.get("KARMA_XPU_DISABLE_EMBREE_DEVICE")
    if engine == "xpu":
        os.environ["KARMA_XPU_DISABLE_EMBREE_DEVICE"] = "1"
    started = time.perf_counter()
    failure = None
    try:
        rop.render(frame_range=(frame, frame))
    except hou.OperationFailed as exc:
        failure = str(exc)
    finally:
        if previous is None:
            os.environ.pop("KARMA_XPU_DISABLE_EMBREE_DEVICE", None)
        else:
            os.environ["KARMA_XPU_DISABLE_EMBREE_DEVICE"] = previous
    seconds = time.perf_counter() - started
    stdout = out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""
    stderr = err.read_text(encoding="utf-8", errors="replace") if err.is_file() else ""
    info = read_log(stdout, stderr)
    # husk 20.5 can crash while exiting after a time-limited frame, after it has saved the image.
    if failure and not (info["time_limit_reached"] and picture.is_file()):
        raise RuntimeError(f"Karma render failed: {excerpt(stdout, stderr) or failure}")
    if not picture.is_file():
        raise RuntimeError("Karma finished without writing an image")
    effective = {name: rop.evalParm(parm) for name, parm in PARMS.items()}
    effective.update(motion_blur=bool(effective["motion_blur"]), depth_of_field=bool(effective["depth_of_field"]),
                     time_limit=rop.evalParm("timelimit") if rop.evalParm("addtimelimit") else None,
                     convert_materials=report is not None)
    return {"file": picture.name, "log": out.name, "frame": frame, "camera": cam.path(), "rop": rop.path(),
            "temporary_rop": temporary, "resolution": [width, height], "settings": effective,
            "status": "time_limit" if info["time_limit_reached"] else "completed", "seconds": round(seconds, 2),
            "lights": len(lit), "materials": report, "notes": notes(engine, mats, len(lit), report), **info}


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
