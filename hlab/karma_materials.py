"""Swap materials Karma cannot read for MaterialX equivalents in the loaded scene only. Imported inside hython."""
import json

import hou

LEGACY = ("v_constant", "v_plastic", "v_metal", "v_glass", "v_decal", "v_supermat", "principledshader")
WRAP = {"repeat": "periodic", "clamp": "clamp", "mirror": "mirror", "decal": "constant", "black": "constant"}


def objects():
    return [n for n in hou.node("/obj").allSubChildren() if isinstance(n, hou.ObjNode)]


def is_light(n):
    base = n.type().name().split("::")[0]
    return "light" in base and base != "indirectlight"


def material_kind(node):
    if node is None:
        return "missing"
    if node.type().category().name() == "Shop":
        return "shop"
    base = node.type().name().split("::")[0]
    if base.startswith("principledshader"):
        return "principled"
    if base == "usdpreviewsurface":
        return "preview_surface"
    if base.startswith("mtlx") or node.isNetwork() and any(
            c.type().name().startswith("mtlx") for c in node.allSubChildren()):
        return "materialx"
    return "vex"


def used():
    """Materials reached by rendered geometry, with each object's original reference text."""
    found, bare = {}, []
    for obj in objects():
        sop = obj.renderNode()
        if sop is None or not obj.isObjectDisplayed() or obj.type().name() == "cam" or is_light(obj):
            continue
        refs = []
        parm = obj.parm("shop_materialpath")
        if parm is not None and parm.evalAsString():
            refs.append((parm.evalAsString(), "object"))
        try:
            attrib = sop.geometry().findPrimAttrib("shop_materialpath")
        except Exception:
            attrib = None
        if attrib is not None:
            refs.extend((text, "primitive") for text in attrib.strings() if text)
        if not refs:
            bare.append(obj.path())
        for text, via in refs:
            node = obj.node(text)
            entry = found.setdefault(node.path() if node else text, {"node": node, "kind": material_kind(node), "uses": []})
            entry["uses"].append((obj, text, via))
    return found, bare


def base_name(node):
    return node.type().name().split("::")[0]


def textured(node):
    return any(p.name().endswith("_useTexture") and p.eval() for p in node.parms())


def handling(entry, engine):
    """convert, keep, or the reason it cannot render as authored."""
    node, kind = entry["node"], entry["kind"]
    if kind == "shop":
        return "convert" if base_name(node) in LEGACY else "Karma 不读这种旧式 /shop 材质，也无法自动转换"
    if kind == "principled" and engine == "xpu" and textured(node):
        return "convert"
    if kind == "vex" and engine == "xpu":
        return "XPU 不支持这个 VEX 材质，也无法自动转换；改用 engine=cpu"
    return "keep"


class Network:
    def __init__(self, source):
        self.parent, self.name = hou.node("/mat"), "hr_karma_" + source.name()

    def node(self, kind, suffix=""):
        return self.parent.createNode(kind, self.name + suffix)


def value(src, name, default):
    parm = src.parm(name)
    return parm.eval() if parm is not None else default


def color(src, name, default=(1., 1., 1.)):
    parms = src.parmTuple(name)
    return tuple(parms.eval()) if parms is not None else default


def point_color(net, suffix="_cd"):
    # Houdini hands the Cd attribute to Karma as the displayColor primvar.
    cd = net.node("mtlxgeompropvalue", suffix)
    cd.parm("signature").set("color3")
    cd.parm("geomprop").set("displayColor")
    cd.parmTuple("default_color3").set((1, 1, 1))
    return cd


def texture(net, path, suffix, wrap="repeat"):
    image = net.node("mtlximage", suffix)
    image.parm("signature").set("color3")
    image.parm("file").set(path)
    for axis in ("uaddressmode", "vaddressmode"):
        image.parm(axis).set(WRAP.get(wrap, "periodic"))
    return image


def feed(net, surface, name, tint, sources):
    """Connect tint × each source to a color3 input, or set the plain tint."""
    if not sources:
        surface.parmTuple(name).set(tint)
        return
    current = sources[0]
    for i, other in enumerate([*sources[1:], None]):
        if other is None and tuple(tint) == (1., 1., 1.):
            break
        product = net.node("mtlxmultiply", f"_{name}_{i}")
        product.parm("signature").set("color3")
        product.setNamedInput("in1", current, 0)
        if other is None:
            product.parmTuple("in2_color3").set(tint)
        else:
            product.setNamedInput("in2", other, 0)
        current = product
    surface.setNamedInput(name, current, 0)


def constant(src, net):
    surface = net.node("mtlxsurface_unlit")
    feed(net, surface, "emission_color", color(src, "clr"), [point_color(net)])
    surface.parm("emission").set(1)
    surface.parm("opacity").set(value(src, "alpha", 1.))
    return surface, ["无光照：颜色 × 几何颜色直接发光"]


def plastic(src, net):
    surface = net.node("mtlxstandard_surface")
    feed(net, surface, "base_color", color(src, "diff"), [point_color(net)])
    surface.parm("specular").set(min(1., max(color(src, "spec", (.2, .2, .2)))))
    surface.parm("specular_roughness").set(value(src, "rough", .2))
    return surface, ["高光按物理材质近似"]


def metal(src, net):
    surface = net.node("mtlxstandard_surface")
    feed(net, surface, "base_color", color(src, "spec"), [point_color(net)])
    surface.parm("metalness").set(1)
    surface.parm("specular_roughness").set(value(src, "rough", .1))
    return surface, ["金属颜色取高光色，环境贴图未转换"]


def glass(src, net):
    surface = net.node("mtlxstandard_surface")
    eta = value(src, "eta", .8)
    surface.parm("base").set(0)
    surface.parm("transmission").set(1)
    surface.parmTuple("transmission_color").set(color(src, "transmit"))
    surface.parm("specular_IOR").set(1 / eta if 0 < eta < 1 else max(eta, 1.))
    surface.parm("specular_roughness").set(value(src, "rough", .1))
    return surface, ["折射率按 eta 换算，衰减和环境贴图未转换"]


def decal(src, net):
    surface = net.node("mtlxstandard_surface")
    sources = [point_color(net)]
    if value(src, "map", ""):
        sources.append(texture(net, value(src, "map", ""), "_map", value(src, "uwrap", "decal")))
    feed(net, surface, "base_color", color(src, "diff"), sources)
    surface.parm("specular_roughness").set(value(src, "rough", .1))
    return surface, ["贴图按 UV 采样，高光按物理材质近似"]


def supermat(src, net):
    surface = net.node("mtlxstandard_surface")
    sources = [point_color(net)]
    if value(src, "diffmap", ""):
        sources.append(texture(net, value(src, "diffmap", ""), "_diffmap"))
    feed(net, surface, "base_color", color(src, "diff"), sources)
    surface.parm("specular_roughness").set(value(src, "srough", .05))
    emit = color(src, "emit", (0., 0., 0.))
    if any(emit):
        surface.parm("emission").set(1)
        surface.parmTuple("emission_color").set(emit)
    return surface, ["只转了漫反射、粗糙度、发光和漫反射贴图；透明、反射和其他贴图未转换"]


def principled(src, net):
    surface = net.node("mtlxstandard_surface")
    sources = [point_color(net)] if value(src, "basecolor_usePointColor", 0) else []
    if value(src, "basecolor_useTexture", 0) and value(src, "basecolor_texture", ""):
        sources.append(texture(net, value(src, "basecolor_texture", ""), "_basecolor",
                               value(src, "basecolor_textureWrap", "repeat")))
    feed(net, surface, "base_color", color(src, "basecolor", (.2, .2, .2)), sources)
    surface.parm("base").set(value(src, "albedomult", 1.))
    surface.parm("metalness").set(value(src, "metallic", 0.))
    surface.parm("specular").set(min(1., 2 * value(src, "reflect", .5)))
    surface.parm("specular_roughness").set(value(src, "rough", .3))
    surface.parm("specular_IOR").set(value(src, "ior", 1.5))
    surface.parm("transmission").set(value(src, "transparency", 0.))
    surface.parmTuple("transmission_color").set(color(src, "transcolor"))
    surface.parm("coat").set(value(src, "coat", 0.))
    surface.parm("coat_roughness").set(value(src, "coatrough", 0.))
    surface.parm("sheen").set(value(src, "sheen", 0.))
    surface.parm("subsurface").set(value(src, "sss", 0.))
    surface.parmTuple("subsurface_color").set(color(src, "ssscolor"))
    emitted = [point_color(net, "_emit_cd")] if value(src, "emitcolor_usePointColor", 0) else []
    feed(net, surface, "emission_color", color(src, "emitcolor"), emitted)
    surface.parm("emission").set(value(src, "emitint", 0.))
    surface.parmTuple("opacity").set(tuple(value(src, "opac", 1.) * c for c in color(src, "opaccolor")))
    notes = ["高光、次表面和光泽按 MaterialX 近似"]
    skipped = [p.name()[:-len("_useTexture")] for p in src.parms()
               if p.name().endswith("_useTexture") and p.eval() and p.name() != "basecolor_useTexture"]
    if skipped:
        notes.append("未转换的贴图：" + "、".join(skipped))
    if value(src, "baseBumpAndNormal_enable", 0):
        notes.append("凹凸和法线贴图未转换")
    return surface, notes


BUILDERS = {"v_constant": constant, "v_plastic": plastic, "v_metal": metal, "v_glass": glass,
            "v_decal": decal, "v_supermat": supermat, "principledshader": principled}


def plan(engine):
    found, _ = used()
    rows = []
    for path, entry in sorted(found.items()):
        how = handling(entry, engine)
        if how != "keep":
            rows.append({"source": path, "type": entry["node"].type().nameWithCategory() if entry["node"] else None,
                         "action": "convert" if how == "convert" else "unsupported", **({} if how == "convert" else {"reason": how})})
    return rows


def convert(engine):
    found, _ = used()
    converted, unconverted, targets = [], [], {}
    for path, entry in sorted(found.items()):
        how = handling(entry, engine)
        if how == "keep":
            continue
        node = entry["node"]
        if how != "convert":
            unconverted.append({"source": path, "type": node.type().nameWithCategory() if node else None, "reason": how})
            continue
        surface, notes = BUILDERS[base_name(node)](node, Network(node))
        for obj, text, via in entry["uses"]:
            plan_ = targets.setdefault(obj, {"object": None, "primitive": {}})
            if via == "object":
                plan_["object"] = surface.path()
            else:
                plan_["primitive"][text] = surface.path()
        converted.append({"source": path, "type": node.type().nameWithCategory(), "material": surface.path(),
                          "objects": len({obj.path() for obj, _, _ in entry["uses"]}), "notes": notes})
    for obj, plan_ in targets.items():
        retarget(obj, plan_)
    return {"converted": converted, "unconverted": unconverted}


def retarget(obj, plan_):
    # Conversion runs only in the unsaved render worker's copy of the HIP.
    # Unlock ancestors first so nested assets can be edited without changing
    # their definitions or the source HIP on disk.
    ancestry = [obj] if plan_["primitive"] else []
    parent = obj.parent()
    while parent is not None:
        ancestry.append(parent)
        parent = parent.parent()
    for node in reversed(ancestry):
        if node.isLockedHDA():
            node.allowEditingOfContents()
    if plan_["object"]:
        parm = obj.parm("shop_materialpath")
        parm.deleteAllKeyframes()
        parm.set(plan_["object"])
    if plan_["primitive"]:
        sop = obj.renderNode()
        shown = sop.isDisplayFlagSet()
        old, new = zip(*sorted(plan_["primitive"].items()))
        swap = obj.createNode("attribwrangle", "hr_karma_materials")
        swap.setInput(0, sop)
        swap.parm("class").set(1)
        swap.parm("snippet").set(
            f"string old[] = {{{', '.join(map(json.dumps, old))}}};\n"
            f"string new[] = {{{', '.join(map(json.dumps, new))}}};\n"
            "int i = find(old, s@shop_materialpath);\nif (i >= 0) s@shop_materialpath = new[i];")
        swap.setRenderFlag(True)
        if shown:
            swap.setDisplayFlag(True)
