"""Swap materials Karma cannot read for MaterialX equivalents in the loaded scene only. Imported inside hython."""
import json

import hou

LEGACY = ("v_constant", "v_plastic", "v_metal", "v_glass", "v_decal", "v_supermat", "principledshader")
WRAP = {"repeat": "periodic", "clamp": "clamp", "streak": "clamp", "mirror": "mirror", "decal": "constant", "black": "constant"}
SPACES = {"linear": "lin_rec709", "raw": "Raw", "sRGB": "srgb_texture", "rec709": "rec709_display"}
# Principled colour inputs: texture prefix, standard_surface input, constant parameter and its default.
COLORS = (("basecolor", "base_color", "basecolor", (.2, .2, .2)), ("transcolor", "transmission_color", "transcolor", (1., 1., 1.)),
          ("ssscolor", "subsurface_color", "ssscolor", (1., 1., 1.)), ("emitcolor", "emission_color", "emitcolor", (1., 1., 1.)),
          ("opaccolor", "opacity", "opaccolor", (1., 1., 1.)))
# Scalar inputs: prefix, input, default and factor. A texture multiplies the value, as Karma CPU renders it.
SCALARS = (("rough", "specular_roughness", .3, 1.), ("metallic", "metalness", 0., 1.), ("reflect", "specular", .5, 2.),
           ("coat", "coat", 0., 1.), ("coatrough", "coat_roughness", 0., 1.), ("transparency", "transmission", 0., 1.),
           ("sss", "subsurface", 0., 1.), ("sheen", "sheen", 0., 1.))
UNMAPPED = ("aniso", "anisodir", "dispersion", "ior", "occlusion", "reflecttint", "sheentint", "sssdist", "transdist")


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


def xpu_gaps(node):
    """Principled features XPU's own fallback drops and a MaterialX conversion restores, found by rendering against
    Karma CPU. Its colour, roughness, metal, normal, emission and opacity textures, glass, coat, sheen and point
    colour render correctly. Subsurface is also dropped, but the converted look was further from CPU."""
    gaps = []
    if value(node, "baseBumpAndNormal_enable", 0) and value(node, "baseBumpAndNormal_type", "") == "bump":
        gaps.append("凹凸贴图")
    if value(node, "transparency_useTexture", 0) and value(node, "transparency_texture", ""):
        gaps.append("透明度贴图")
    return gaps


def handling(entry, engine):
    """convert, keep, or the reason it cannot render as authored."""
    node, kind = entry["node"], entry["kind"]
    if kind == "shop":
        return "convert" if base_name(node) in LEGACY else "Karma 不读这种旧式 /shop 材质，也无法自动转换"
    if kind == "principled" and engine == "xpu" and xpu_gaps(node):
        return "convert"
    if kind == "principled" and engine == "xpu" and value(node, "sss", 0.) > 0:
        return "XPU 会忽略次表面散射，这部分会和 CPU 不同；要准确效果用 engine=cpu"
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


def texture(net, path, suffix, wrap="repeat", signature="color3", space="auto"):
    image = net.node("mtlximage", suffix)
    image.parm("signature").set(signature)
    image.parm("file").set(path)
    # Principled's automatic space is left to the image reader, as Karma CPU does.
    if space != "auto":
        image.parm("filecolorspace").set(SPACES.get(space, space))
    for axis in ("uaddressmode", "vaddressmode"):
        image.parm(axis).set(WRAP.get(wrap, "periodic"))
    return image


def channel(net, src, prefix, signature="color3"):
    """The mtlximage for an enabled <prefix>_texture, or None."""
    if not value(src, prefix + "_useTexture", 0) or not value(src, prefix + "_texture", ""):
        return None
    return texture(net, value(src, prefix + "_texture", ""), "_" + prefix, value(src, prefix + "_textureWrap", "repeat"),
                   signature, value(src, prefix + "_textureColorSpace", "auto"))


def mono(net, image, pick, suffix):
    """Principled mono channel: 0 luminance, 1 red, 2 green, 3 blue."""
    source = image
    if pick == 0:
        source = net.node("mtlxluminance", suffix + "_luma")
        source.parm("signature").set("color3")
        source.setNamedInput("in", image, 0)
    single = net.node("mtlxextract", suffix + "_mono")
    single.parm("signature").set("color3")
    single.setNamedInput("in", source, 0)
    single.parm("index").set(max(0, pick - 1))
    return single


def scaled(net, source, amount, suffix):
    if amount == 1:
        return source
    product = net.node("mtlxmultiply", suffix)
    product.setNamedInput("in1", source, 0)
    product.parm("in2").set(amount)
    return product


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


def relief(net, src):
    """standard_surface normal from Principled's base bump or normal map."""
    if not value(src, "baseBumpAndNormal_enable", 0):
        return None, []
    if value(src, "baseBumpAndNormal_type", "bump") == "normal":
        if not value(src, "baseNormal_texture", ""):
            return None, []
        image = texture(net, value(src, "baseNormal_texture", ""), "_normal_image", value(src, "baseNormal_wrap", "repeat"),
                        "vector3", "raw")
        mapped = net.node("mtlxnormalmap", "_normal")
        mapped.setNamedInput("in", image, 0)
        mapped.parm("scale").set(value(src, "baseNormal_scale", 1.))
        notes = []
        if value(src, "baseNormal_flipX", 0) or value(src, "baseNormal_flipY", 0):
            notes.append("法线贴图的 X/Y 翻转未转换")
        if value(src, "baseNormal_vectorSpace", "uvtangent") != "uvtangent":
            notes.append("法线贴图只按切线空间转换")
        return mapped, notes
    if not value(src, "baseBump_bumpTexture", ""):
        return None, []
    image = texture(net, value(src, "baseBump_bumpTexture", ""), "_bump_image", value(src, "baseBump_wrap", "repeat"),
                    "default", "raw")
    bump = net.node("mtlxbump", "_bump")
    bump.setNamedInput("height", image, 0)
    bump.parm("scale").set(value(src, "baseBump_bumpScale", .05))
    return bump, ["凹凸强度沿用原数值"]


def principled(src, net):
    surface = net.node("mtlxstandard_surface")
    for prefix, name, parm, default in COLORS:
        tint = color(src, parm, default)
        if prefix == "opaccolor":
            tint = tuple(c * value(src, "opac", 1.) for c in tint)
        sources = [point_color(net, f"_{prefix}_cd")] if value(src, prefix + "_usePointColor", 0) else []
        image = channel(net, src, prefix)
        if image is not None:
            sources.append(image)
            tint = tuple(c * value(src, prefix + "_textureIntensity", 1.) for c in tint)
        feed(net, surface, name, tint, sources)
    for prefix, name, default, factor in SCALARS:
        amount = value(src, prefix, default) * factor
        image = channel(net, src, prefix)
        if image is None:
            surface.parm(name).set(min(1., amount) if prefix == "reflect" else amount)
        else:
            single = mono(net, image, int(value(src, prefix + "_monoChannel", 0)), "_" + prefix)
            surface.setNamedInput(name, scaled(net, single, amount, f"_{prefix}_amount"), 0)
    surface.parm("base").set(value(src, "albedomult", 1.))
    surface.parm("specular_IOR").set(value(src, "ior", 1.5))
    surface.parm("emission").set(value(src, "emitint", 0.))
    normal, notes = relief(net, src)
    if value(src, "sss", 0.) > 0:
        notes.append("次表面散射比 CPU 偏均匀")
    if value(src, "sheen", 0.) > 0:
        notes.append("光泽（sheen）比 CPU 偏强")
    if normal is not None:
        surface.setNamedInput("normal", normal, 0)
    notes.insert(0, "按 MaterialX standard_surface 近似")
    skipped = [prefix for prefix in UNMAPPED if value(src, prefix + "_useTexture", 0)]
    if skipped:
        notes.append("未转换的贴图：" + "、".join(skipped))
    if value(src, "coat", 0.) > 0 and value(src, "separateCoatNormals", 0) and value(src, "coatBumpAndNormal_enable", 0):
        notes.append("清漆层自己的凹凸和法线未转换")
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
        if entry["kind"] == "principled":
            notes.insert(0, "XPU 自带的近似会丢掉" + "、".join(xpu_gaps(node)))
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
