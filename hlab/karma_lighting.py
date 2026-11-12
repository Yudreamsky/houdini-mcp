"""Light the loaded scene with a lighting look, without saving it. Imported inside hython only."""
import math

import hou

from hlab.karma_materials import is_light, objects
from hlab.karma_sky import DISC, camera_frame, design, unit, write_hdr

PREFIX = "HR_KARMA_"
DIRECTIONS = {0: "相机方向", 45: "右前方", 90: "右侧", 135: "右后方", 180: "物体正后方，逆光", -45: "左前方", -90: "左侧", -135: "左后方"}


def outdoor(node):
    """Sky and sun lights, which a look always replaces."""
    if node.type().name().split("::")[0] == "envlight":
        return True
    kind = node.parm("light_type")
    return kind is not None and kind.evalAsString() in ("distant", "sun")


def subject():
    """Centre and radius of everything that renders: the studio rig is sized and placed from it."""
    low, high = [math.inf] * 3, [-math.inf] * 3
    for node in objects():
        sop = node.renderNode()
        if sop is None or not node.isObjectDisplayed() or node.type().name() == "cam" or is_light(node):
            continue
        try:
            geo = sop.geometry()
        except hou.Error:
            continue
        if geo is None or not geo.intrinsicValue("pointcount"):
            continue
        box, world = geo.boundingBox(), node.worldTransform()
        for x in (box.minvec()[0], box.maxvec()[0]):
            for y in (box.minvec()[1], box.maxvec()[1]):
                for z in (box.minvec()[2], box.maxvec()[2]):
                    p = hou.Vector3(x, y, z) * world
                    low = [min(a, b) for a, b in zip(low, p)]
                    high = [max(a, b) for a, b in zip(high, p)]
    if low[0] == math.inf:
        return (0., 0., 0.), 1.
    centre = tuple((a + b) / 2 for a, b in zip(low, high))
    return centre, max(.001, math.dist(low, high) / 2)


def view(cam, forward):
    """The camera's view direction and the angle from it to the picture's corner, which centre the studio backdrop."""
    try:
        across = cam.evalParm("aperture") / 2. / cam.evalParm("focal")
        corner = math.atan(math.hypot(across, across * cam.evalParm("resy") / cam.evalParm("resx")))
    except (hou.Error, TypeError, ZeroDivisionError):
        corner = math.radians(25.)
    return unit(forward), min(max(corner, math.radians(5.)), math.radians(70.))


def aim(node, position, target):
    up = hou.Vector3(0, 1, 0)
    if abs((target - position).normalized().dot(up)) > .999:
        up = hou.Vector3(0, 0, -1)
    node.setWorldTransform(hou.hmath.buildRotateLookAt(position, target, up) * hou.hmath.buildTranslate(position))


def extend(rop, name, paths):
    parm = rop.parm(name)
    if parm is not None and paths:
        parm.set(" ".join([parm.evalAsString().strip(), *paths]).strip())


def where(angle):
    near = min(DIRECTIONS, key=lambda a: abs((angle - a + 180) % 360 - 180))
    return DIRECTIONS[near]


def apply(look, cam, rop, folder):
    """Replace the scene's sky and sun (and its other lights unless kept) with the look's temporary lights."""
    world = cam.worldTransform()
    forward, up = hou.Vector4(0, 0, -1, 0) * world, hou.Vector4(0, 1, 0, 0) * world
    frame = camera_frame(tuple(forward)[:3], tuple(up)[:3])
    lights, sky_rows = design(look["look"], frame, look["angle"], look["elevation"], look.get("fill", 0.),
                              view(cam, tuple(forward)[:3]))
    turned_off, kept = [], []
    for node in objects():
        if not is_light(node) or not node.isObjectDisplayed():
            continue
        enabled = node.parm("light_enable")
        if enabled is not None and not enabled.eval():
            continue
        if look["keep_scene_lights"] and not outdoor(node):
            kept.append(node.path())
            continue
        turned_off.append(node.path())
        try:
            if enabled is not None:
                enabled.set(0)
        except hou.Error:
            pass  # Lights inside locked assets are excluded on the ROP below instead.
    obj = hou.node("/obj")
    centre, radius = subject() if look["look"] == "studio" else ((0., 0., 0.), 10.)
    target = hou.Vector3(centre)
    added = []
    for spec in lights:
        node = obj.createNode("hlight::2.0", PREFIX + spec["name"])
        node.parm("light_type").set(spec["type"])
        node.parmTuple("light_color").set(spec["color"])
        node.parm("light_intensity").set(spec["intensity"])
        node.parm("light_exposure").set(look["exposure"])
        if spec["type"] == "sun":
            node.parm("vm_envangle").set(DISC / 2.)  # Houdini's sun angle is the half angle; USD gets twice it
            aim(node, target + hou.Vector3(spec["toward"]) * radius, target)
        else:
            node.parmTuple("areasize").set(tuple(s * radius for s in spec["size"]))
            node.parm("normalizearea").set(0)
            aim(node, target + hou.Vector3(spec["toward"]) * spec["distance"] * radius, target)
        added.append(node.path())
    sky = folder / "sky.hdr"
    write_hdr(sky, sky_rows)
    env = obj.createNode("envlight", PREFIX + "SKY")
    env.parm("env_map").set(str(sky))
    env.parm("light_exposure").set(look["exposure"])
    env.parm("light_contribprimary").set(1)  # the sky is also the background
    added.append(env.path())
    extend(rop, "excludelights", turned_off)
    extend(rop, "lights", added)
    if rop.evalParm("sololights").strip():
        extend(rop, "sololights", added)
    report = {**look, "added": added, "turned_off": turned_off, "kept": kept}
    if look["look"] == "studio":
        report["subject"] = {"centre": [round(c, 4) for c in centre], "radius": round(radius, 4)}
    return report


def notes(report):
    look, rows = report["look"], []
    text = f"灯光用「{report['label']}」，临时加了 {len(report['added'])} 盏灯，工程文件不变"
    source = {"day": "太阳", "overcast": "云后的太阳", "night": "月亮", "studio": "主光"}[look]
    text += f"；{source}在{where(report['angle'])}（{report['angle']:g}°），高 {report['elevation']:g}°"
    if report.get("fill"):
        text += f"；{'天光' if look in ('day', 'night') else '辅光'}{report['fill']:+g} 档"
    rows.append(text + "。")
    if report["turned_off"]:
        rows.append(f"关掉了工程里的 {len(report['turned_off'])} 盏灯（如 {report['turned_off'][0]}）"
                    + ("；天空和太阳类的灯总会被替换。" if report["keep_scene_lights"] else "；要保留局部灯可传 keep_scene_lights=true。"))
    if report["kept"]:
        rows.append(f"保留了工程里的 {len(report['kept'])} 盏局部灯（如 {report['kept'][0]}）"
                    + ("，夜景靠它们点亮；不要可传 keep_scene_lights=false。" if look == "night" else "。"))
    elif look == "night":
        rows.append("工程里没有自己的灯，夜景只有月光和夜空，主要看剪影；要看清形体，可把月亮转到前侧（light_angle=-60）"
                    "或加 light_exposure，也可在工程里加灯。")
    if look == "studio":
        rows.append(f"摄影棚的灯按全部几何体的范围摆放（半径约 {report['subject']['radius']:g}）；"
                    "有很大的地面时灯会离得远，但亮度不变。")
    return rows
