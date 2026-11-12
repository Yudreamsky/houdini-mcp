"""Export the loaded HIP for Chaos Vantage without saving it: one flattened USD file plus what the host needs to run
vantage_console and put the sky behind the result. Imported inside hython only.

Vantage 3.3 reads USD through V-Ray's importer, which differs from Karma in ways measured on the tower crane sample
and on matte test cards: only MaterialX shading, no primvars inside MaterialX, no automatic smoothing, a brighter
default grey, a USD dome that lights the scene but never shows behind it, the sequence camera taken from the render
settings, and lights brighter by an amount that depends on the light's type."""
import math
import time

import hou
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdRender, UsdShade

from hlab import karma_lighting
from hlab.karma_materials import convert, objects
from hlab.karma_render import (apply_scene, fix_materials, lights, materials, notes as material_notes,
                               photoreal_notes, pick_camera, scene_notes, whole)
from hlab.karma_spec import lighting, resolution

PREFIX = "HR_VANTAGE_"
# How much brighter Vantage 3.3.1 shows the same USD light than Karma 20.5, measured on matte cards of known albedo.
BRIGHTER = {"DistantLight": 1.1, "SphereLight": 1.1, "CylinderLight": 1.3, "RectLight": 1.44, "DiskLight": 1.44,
            "DomeLight": 1.43}
UNMEASURED = 1.2
# Karma shades a mesh without a material like a 0.4 grey with an ordinary 4% reflection; Vantage's own default is
# about a fifth brighter.
KARMA_GREY = .41
DEFAULT_MATERIAL = "/HR_VANTAGE/default_grey"


def geometry_objects():
    return [o for o in objects() if o.type().name() == "geo" and o.isObjectDisplayed() and o.renderNode() is not None]


def append(obj, kind, name):
    """A SOP after the object's render node that becomes the new display and render node, or None when locked."""
    try:
        node = obj.createNode(kind, PREFIX + name)
    except hou.Error:
        return None
    node.setInput(0, obj.renderNode())
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return node


def normals():
    """Vantage shades polygons flat unless they carry normals; Karma smooths them itself."""
    added = 0
    for obj in geometry_objects():
        geo = obj.renderNode().geometry()
        if geo is None or geo.findPointAttrib("N") or geo.findVertexAttrib("N") or not geo.intrinsicValue("primitivecount"):
            continue
        node = append(obj, "normal", "NORMALS")
        if node is not None:
            node.parm("cuspangle").set(60)
            added += 1
    return added


def bevel(millimetres):
    """Real rounded edges: Vantage cannot read Karma's rounded-edge shading, so hard edges are bevelled."""
    done, failed = 0, []
    for obj in geometry_objects():
        node = append(obj, "polybevel::3.0", "BEVEL")
        if node is None:
            failed.append(obj.path())
            continue
        node.parm("offset").set(millimetres / 1000.)
        node.parm("ignoreflatedges").set(1)
        node.parm("flatangle").set(30)  # smooth surfaces keep their shape; only creases are rounded
        node.parm("filletshape").set("round")
        node.parm("divisions").set(3)
        try:
            node.cook(force=True)
        except hou.OperationFailed:
            # Leave this object sharp rather than lose it.
            previous = node.inputs()[0]
            node.destroy()
            previous.setDisplayFlag(True)
            previous.setRenderFlag(True)
            failed.append(obj.path())
            continue
        # Weighting by face area keeps big faces flat and curves only the fillet; vertex-angle weighting would
        # bend whole faces towards their bevels and leave dark lines along the edges.
        smooth = append(obj, "normal", "BEVEL_NORMALS")
        smooth.parm("method").set(2)  # by face area
        done += 1
    return {"millimetres": millimetres, "objects": done, "failed": failed[:12]}


def write_usd(path, first, last):
    importer = hou.node("/stage").createNode("sceneimport::2.0", PREFIX + "IMPORT")
    importer.parm("objects").set("*")
    importer.parm("asreference").set(0)
    rop = hou.node("/out").createNode("usd", PREFIX + "USD")
    rop.parm("loppath").set(importer.path())
    rop.parm("lopoutput").set(str(path))
    rop.parm("savestyle").set("flattenstage")
    rop.parm("ensuremetricsset").set(1)
    if last > first:
        rop.parm("trange").set("normal")
        rop.parmTuple("f").set((first, last, 1))
        # Without a flush per frame the ROP misses object transforms on some frames, most often the last ones, and the
        # animation freezes there (4 of 6 exports of a keyframed ball in one hython; 0 of 6 with the flush).
        rop.parm("fileperframe").set(1)
        rop.render(frame_range=(first, last))
    else:
        rop.parm("trange").set("off")
        rop.render()


def bake_point_colour(stage, start):
    """Vantage does not read primvars inside MaterialX: a geompropvalue(displayColor) becomes the colour of the meshes
    bound to its material when they all agree."""
    colours = {}
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        primvar = UsdGeom.PrimvarsAPI(prim).GetPrimvar("displayColor")
        material = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        if material and primvar and primvar.HasValue():
            values = primvar.Get(start) or []
            colours.setdefault(material.GetPath(), set()).update(tuple(round(c, 4) for c in v) for v in values)
    baked, mixed = [], []
    for path, values in colours.items():
        readers = [p for p in Usd.PrimRange(stage.GetPrimAtPath(path))
                   if p.GetTypeName() == "Shader" and UsdShade.Shader(p).GetIdAttr().Get() == "ND_geompropvalue_color3"]
        if not readers:
            continue
        if len(values) != 1:
            mixed.append(str(path))
            continue
        colour = Gf.Vec3f(*next(iter(values)))
        for shader in Usd.PrimRange(stage.GetPrimAtPath(path)):
            if shader.GetTypeName() != "Shader":
                continue
            for entry in UsdShade.Shader(shader).GetInputs():
                sources = entry.GetConnectedSources()[0] if entry.HasConnectedSource() else []
                if any(s.source.GetPrim() in readers for s in sources):
                    entry.DisconnectSource()
                    entry.Set(colour)
        baked.append(str(path))
    return baked, mixed


def number(value):
    return tuple(float(v) for v in value) if hasattr(value, "__len__") else float(value)


def combined(op, a, b):
    if isinstance(a, tuple) or isinstance(b, tuple):
        size = len(a) if isinstance(a, tuple) else len(b)
        a, b = (v if isinstance(v, tuple) else (v,) * size for v in (a, b))
        return tuple(op(x, y) for x, y in zip(a, b))
    return op(a, b)


ARITHMETIC = {"multiply": lambda x, y: x * y, "add": lambda x, y: x + y, "subtract": lambda x, y: x - y}


def evaluated(prim, varying, depth=0):
    """The constant a shader node outputs when nothing upstream varies, else None. Images, primvars that differ
    from mesh to mesh and inputs left at an unknown default all count as varying."""
    shader = UsdShade.Shader(prim)
    parts = (shader.GetIdAttr().Get() or "").split("_")
    op = parts[1] if len(parts) > 2 and parts[0] == "ND" else ""
    if depth > 16 or op not in ("geompropvalue", "constant", *ARITHMETIC):
        return None
    if op == "geompropvalue":
        default = shader.GetInput("default")
        return None if str(prim.GetPath()) in varying or not default or default.Get() is None else number(default.Get())
    values = {}
    for entry in shader.GetInputs():
        if entry.HasConnectedSource():
            value = evaluated(entry.GetConnectedSources()[0][0].source.GetPrim(), varying, depth + 1)
        else:
            value = entry.Get()
            value = None if value is None else number(value)
        if value is None:
            return None
        values[entry.GetBaseName()] = value
    if op == "constant":
        return values.get("value")
    if "in1" not in values or "in2" not in values:
        return None
    return combined(ARITHMETIC[op], values["in1"], values["in2"])


def fold_constants(stage, mixed):
    """Replace node chains without textures by the constant they compute. Vantage shades the camera's view of such
    a chain correctly but lights its surroundings as if the surface were white (measured: a blue box threw white
    light on the ground), while textures and plain values bounce their real colour. Returns the materials changed."""
    varying = set()
    for path in mixed:
        varying.update(str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(path))
                       if p.GetTypeName() == "Shader" and "geompropvalue" in (UsdShade.Shader(p).GetIdAttr().Get() or ""))
    changed = set()
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Shader" or "surface" not in (UsdShade.Shader(prim).GetIdAttr().Get() or ""):
            continue
        for entry in UsdShade.Shader(prim).GetInputs():
            if not entry.HasConnectedSource():
                continue
            value = evaluated(entry.GetConnectedSources()[0][0].source.GetPrim(), varying)
            if value is None:
                continue
            entry.DisconnectSource()
            entry.Set(Gf.Vec3f(*value) if isinstance(value, tuple) else value)
            changed.add(str(prim.GetParent().GetPath()))
    return sorted(changed)


def camera_prim(stage, cam):
    found = [p for p in stage.Traverse() if p.GetTypeName() == "Camera" and p.GetName() == cam.name()]
    exact = [p for p in found if str(p.GetPath()).endswith(cam.path()[len("/obj"):])]
    return (exact or found or [None])[0]


def default_grey(stage):
    """Meshes without a material and without their own colour get Karma's default grey; returns how many."""
    bare = []
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh" or UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]:
            continue
        # Per-face materials (shop_materialpath on primitives) arrive as bound subsets; a mesh they cover is not bare.
        covered = set()
        for subset in UsdGeom.Subset.GetAllGeomSubsets(UsdGeom.Imageable(prim)):
            if UsdShade.MaterialBindingAPI(subset.GetPrim()).ComputeBoundMaterial()[0]:
                covered.update(subset.GetIndicesAttr().Get() or [])
        if covered and len(covered) >= len(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or []):
            continue
        colour = UsdGeom.PrimvarsAPI(prim).GetPrimvar("displayColor")
        if not (colour and colour.HasValue()):
            bare.append(prim)
    if bare:
        material = UsdShade.Material.Define(stage, DEFAULT_MATERIAL)
        shader = UsdShade.Shader.Define(stage, DEFAULT_MATERIAL + "/surface")
        shader.CreateIdAttr("ND_standard_surface_surfaceshader")
        shader.CreateInput("base", Sdf.ValueTypeNames.Float).Set(1.)
        shader.CreateInput("base_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(KARMA_GREY))
        shader.CreateInput("specular_roughness", Sdf.ValueTypeNames.Float).Set(.5)
        material.CreateSurfaceOutput("mtlx").ConnectToSource(shader.CreateOutput("out", Sdf.ValueTypeNames.Token))
        for prim in bare:
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    return len(bare)


def match_lights(stage):
    """Lower each light by what Vantage adds for its type; returns the factors used, by type."""
    used = {}
    for prim in stage.Traverse():
        if prim.HasAPI(UsdLux.LightAPI) or prim.GetTypeName().endswith("Light"):
            kind = prim.GetTypeName().split("_")[0]  # DomeLight_1 is a newer DomeLight
            used[kind] = BRIGHTER.get(kind, UNMEASURED)
            exposure = prim.GetAttribute("inputs:exposure")
            if not exposure:
                exposure = prim.CreateAttribute("inputs:exposure", Sdf.ValueTypeNames.Float)
            exposure.Set((exposure.Get() or 0.) - math.log2(used[kind]))
    return used


def finish(path, cam, first, last, width, height):
    """Vantage-specific edits to the exported stage; returns what changed."""
    stage = Usd.Stage.Open(str(path))
    baked, mixed = bake_point_colour(stage, first)
    folded = fold_constants(stage, mixed)
    greyed = default_grey(stage)
    dimmed = match_lights(stage)
    target = camera_prim(stage, cam)
    if target is not None:
        # In sequence mode Vantage ignores -camera and renders the render settings' camera.
        render = UsdRender.Settings.Define(stage, "/Render/rendersettings")
        render.CreateCameraRel().SetTargets([target.GetPath()])
        render.CreateResolutionAttr(Gf.Vec2i(width, height))
        stage.SetMetadata("renderSettingsPrimPath", "/Render/rendersettings")
    stage.SetStartTimeCode(first)
    stage.SetEndTimeCode(last)
    stage.GetRootLayer().Save()
    return {"baked_point_colour": baked, "mixed_point_colour": mixed, "folded_materials": folded,
            "default_grey": greyed, "dimmed_lights": dimmed,
            "camera_prim": str(target.GetPath()) if target is not None else None}


def view(cam, first, last, width, height):
    """What the host needs to draw the sky behind each frame: projection, lens and the camera's world matrices."""
    ortho = cam.evalParm("projection") == 1
    lens = {"projection": "orthographic" if ortho else "perspective", "aspect": height / width,
            "tan_half": cam.evalParm("aperture") / 2. / cam.evalParm("focal")}
    matrices = {}
    for frame in range(int(first), int(last) + 1):
        matrices[str(frame)] = [list(row) for row in cam.worldTransformAtTime(hou.frameToTime(frame)).asTupleOfTuples()]
        if ortho:
            lens.setdefault("ortho_width", cam.parm("orthowidth").evalAtFrame(frame))
    return {**lens, "matrices": matrices}


def sky_lights():
    return [n.path() for n in lights() if n.type().name().split("::")[0] == "envlight" and n.parm("env_map")
            and n.evalParm("env_map")]


def export(req, folder):
    started = time.perf_counter()
    chosen = req["settings"]
    first, last = (whole(f) for f in (req.get("frames") or (hou.frame(), hou.frame())))
    hou.setFrame(first)
    scene = apply_scene(req.get("scene"))
    cam = pick_camera(req.get("camera", ""), None, True)
    if last > first and cam.evalParm("projection") == 1:
        raise ValueError("Vantage cannot animate an orthographic camera from USD (it misreads its width in sequences); "
                         "render stills, use a perspective camera, or use Karma for this shot")
    width, height = resolution((cam.evalParm("resx"), cam.evalParm("resy")), chosen)
    real = {"pbr_fixes": fix_materials(chosen), "round_edges": None}
    report = convert("xpu", force=True)
    for row in report["unconverted"]:
        row["reason"] = "Vantage 只读 MaterialX，这个材质无法自动转换，会按默认材质渲染"
    if chosen.get("round_edges"):
        real["round_edges"] = bevel(chosen["round_edges"])
    smoothed = normals()
    look = lighting(chosen)
    lit_by = karma_lighting.apply(look, cam, None, folder) if look else None
    mats = materials()
    lit = [n for n in lights() if not lit_by or n.path() not in lit_by["turned_off"]]
    usd = folder / "scene.usd"
    write_usd(usd, first, last)
    edits = finish(usd, cam, first, last, width, height)
    rows = scene_notes(scene) + (karma_lighting.notes(lit_by) if lit_by else []) + vantage_notes(real, smoothed, edits, look) \
        + [r for r in material_notes("vantage", mats, len(lit), report) if not r.startswith("场景里没有开着的灯")]
    if not lit:
        rows.insert(0, "场景里没有开着的灯，Vantage 不会自动加灯，画面会是黑的；可用 changes 里的 lighting"
                       "（day、overcast、night、studio）临时布光。")
    if not look and sky_lights():
        rows.append("工程里的环境光贴图在 Vantage 里只照明、不显示为背景，背景会是透明的；用 lighting 预设可以看到天空。")
    return {"usd": usd.name, "camera": cam.path(), "camera_name": cam.name(), "frames": [first, last],
            "resolution": [width, height], "view": view(cam, first, last, width, height),
            "sky": "sky.hdr" if look else None, "lighting": lit_by, "materials": report, "photoreal": real,
            "lights": len(lit), "normals_added": smoothed, "usd_edits": edits, "scene": scene,
            "export_seconds": round(time.perf_counter() - started, 2), "notes": rows}


def vantage_notes(real, smoothed, edits, look):
    rows = []
    bevelled = real.get("round_edges")
    shown = {k: v for k, v in real.items() if k != "round_edges"}
    rows += photoreal_notes(shown)
    if bevelled:
        text = f"给 {bevelled['objects']} 个物体的硬边做了 {bevelled['millimetres']:g} 毫米真实倒角（Vantage 读不了 Karma 的圆角着色）"
        if bevelled["failed"]:
            text += f"；{len(bevelled['failed'])} 个没做成，保持直角（如 {bevelled['failed'][0]}）"
        rows.append(text + "。")
    if smoothed:
        rows.append(f"给 {smoothed} 个没有法线的物体加了平滑法线，Vantage 才不会把曲面渲成一块块平面。")
    if edits["baked_point_colour"]:
        rows.append(f"{len(edits['baked_point_colour'])} 个材质用到几何体颜色，Vantage 读不了，已把颜色写进材质。")
    if edits["mixed_point_colour"]:
        rows.append(f"{len(edits['mixed_point_colour'])} 个材质的几何体颜色各处不同，Vantage 会按材质本色渲染、偏浅"
                    f"（如 {edits['mixed_point_colour'][0]}）。")
    if edits["folded_materials"]:
        rows.append(f"{len(edits['folded_materials'])} 个材质的颜色或数值由节点算出（如几何体颜色 × 底色）：Vantage 算反弹光时"
                    "会把它当成白色、让周围发白，已折算成常数。")
    if edits["default_grey"]:
        rows.append(f"{edits['default_grey']} 个物体没有材质：两个渲染器的默认灰色不一样，已临时给它们和 Karma 一样的灰"
                    f"（反射率 {KARMA_GREY:g}）。")
    if edits["dimmed_lights"]:
        rows.append("同样的灯 Vantage 比 Karma 亮，已按灯的类型调暗到一致（实测：平行光、点光、聚光约 1.1 倍，"
                    "矩形和圆盘面光、环境光约 1.44 倍）。")
    return rows
