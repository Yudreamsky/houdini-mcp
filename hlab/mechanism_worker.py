"""Build self-contained kinematic guides and object constraints under hython."""
import math
from pathlib import Path

import hou
from mechanism_math import rope_path
from rig_worker import key_drive


# Stored inside the HIP so the rig cooks without an installed MCP.
GUIDE_COOK = '''
node = hou.pwd()
geo = node.geometry()
drive = node.parent().evalParm("drive")
if spec["kind"] == "fourbar":
    xy = four_points(spec["ground_a"], spec["ground_d"], spec["crank"], spec["coupler"],
                     spec["rocker"], drive, spec["branch"])
    chain = [(0, 1), (1, 2), (3, 2), (3, 0)]
    points = [geo.createPoint() for p in xy]
    for pt, (x, y) in zip(points, xy):
        pt.setPosition((x, y, spec["z"]))
    for i, (first, second) in enumerate(chain):
        shape = geo.createPolygon(is_closed=False)
        shape.addVertex(points[first])
        shape.addVertex(points[second])
        delta = points[second].position() - points[first].position()
        attribute = geo.addAttrib(hou.attribType.Global, "angle" + str(i), 0.)
        geo.setGlobalAttribValue(attribute, math.degrees(math.atan2(delta[1], delta[0])))
else:
    drop = node.parent().evalParm("drop")
    xy = rope_path(spec["falls"], spec["sheave_radius"], drop)
    shape = geo.createPolygon(is_closed=False)
    for x, y in xy:
        point = geo.createPoint()
        point.setPosition((x, y, 0))
        shape.addVertex(point)
'''


def geometry_obj(path):
    node = hou.node(path)
    if not isinstance(node, hou.ObjNode) or not isinstance(node.displayNode(), hou.SopNode):
        raise ValueError(f"Expected a geometry OBJ: {path}")
    return node


def guide_network(spec):
    net = hou.node(spec["network"])
    if not net or net.childTypeCategory() != hou.objNodeTypeCategory():
        raise ValueError("Choose an OBJ network for the guide")
    g = net.createNode("geo", spec["kind"].upper() + "_CONTROL", run_init_scripts=False)
    is_loop = spec["kind"] == "fourbar"
    label = "Crank angle (degrees)" if is_loop else "Drum turns (positive winds in)"
    g.addSpareParmTuple(hou.FloatParmTemplate("drive", label, 1, (0.,)))
    key_drive(g, spec["keys"])
    if not is_loop:
        g.addSpareParmTuple(hou.FloatParmTemplate("drop", "Hook drop (scene units)", 1))
        g.parm("drop").setExpression(f'{spec["initial_drop"]!r} - ch("drive") * {math.tau * spec["drum_radius"] / spec["falls"]!r}', hou.exprLanguage.Hscript)
    solver = g.createNode("python", "Mechanism_geometry")
    math_code = Path(__file__).with_name("mechanism_math.py").read_text(encoding="utf8")
    constants = {k: v for k, v in spec.items() if k not in ("parts", "keys", "drop_parm", "drum_rotation_parm")}
    solver.parm("python").set("import hou\n" + math_code + "\nspec = " + repr(constants) + "\n" + GUIDE_COOK)
    skin = solver.createOutputNode("polywire", "Visible_linkage" if is_loop else "Visible_rope")
    radius = min(spec["crank"], spec["rocker"], spec["coupler"])*.032 if is_loop else spec["sheave_radius"]*.065
    skin.setParms({"radius": radius, "div": 10})
    skin.setDisplayFlag(True)
    skin.setRenderFlag(True)
    g.layoutChildren()
    g.moveToGoodPosition()
    return g, solver


def checked_geo(path):
    node = hou.node(path)
    geo = node.geometry()
    if geo is None or node.errors() or not geo.intrinsicValue("primitivecount"):
        raise ValueError(f"Guide failed: {path}: {node.errors()}")
    return geo


def fourbar(spec):
    g, solver = guide_network(spec)
    checked_geo(solver.path())
    outputs = {}
    parts = spec["parts"] or []
    if len(set(parts)) != len(parts):
        raise ValueError("Use a different rigid object for each link")
    for i, (path, pivot) in enumerate(zip(parts, (0, 1, 3))):
        part = geometry_obj(path)
        if part.parent() != g.parent() or part.input(0) or any(
                p.keyframes() for name in ("t","r","s","p","pr","scale") for p in (part.parmTuple(name) or ())):
            raise ValueError(f"Select an unparented, static transform in the guide network: {path}")
        rest = part.worldTransform()
        ctrl = g.parent().createNode("null", "LINK_" + part.name())
        ctrl.setDisplayFlag(False)
        ref = ctrl.relativePathTo(solver)
        for j, axis in enumerate("xyz"):
            ctrl.parm("t"+axis).setExpression(f'point("{ref}", {pivot}, "P", {j})', hou.exprLanguage.Hscript)
        ctrl.parm("rz").setExpression(f'detail("{ref}", "angle{i}", 0)', hou.exprLanguage.Hscript)
        part.setInput(0, ctrl)
        part.setWorldTransform(rest, fail_on_locked_parms=True)
        if not part.worldTransform().isAlmostEqual(rest, 1e-6):
            raise ValueError(f"Rest pose mismatch: {path}")
        ctrl.moveToGoodPosition()
        outputs[path] = ctrl.path()
    if outputs:
        g.setDisplayFlag(False)
    return dict(control=g.path(), solver=solver.path(), parts=outputs)


def static_scalar(path):
    p = hou.parm(path)
    if not p or not isinstance(p.parmTemplate(), hou.FloatParmTemplate) or p.keyframes() or p.isLocked():
        raise ValueError(f"Expected an editable static scalar parameter: {path}")
    return p


def reeving(spec):
    g, solver = guide_network(spec)
    drop = static_scalar(spec["drop_parm"]) if spec["drop_parm"] else None
    rotary = static_scalar(spec["drum_rotation_parm"]) if spec["drum_rotation_parm"] else None
    if drop is not None and drop == rotary:
        raise ValueError("Use separate hook-drop and drum-rotation channels")
    for _, turns in spec["keys"]:
        distance = spec["initial_drop"] - math.tau*spec["drum_radius"]*turns/spec["falls"]
        rope_path(spec["falls"], spec["sheave_radius"], distance)
        if drop is not None:
            pt = drop.parmTemplate()
            if (pt.minIsStrict() and distance < pt.minValue()) or (pt.maxIsStrict() and distance > pt.maxValue()):
                raise ValueError("Hook travel exceeds the model channel's limits")
    if drop is not None:
        if abs(drop.eval()-spec["initial_drop"]) > 1e-5:
            raise ValueError("initial_drop must match the source model's neutral hook drop")
        drop.setExpression(f'ch("{drop.node().relativePathTo(g)}/drop")', hou.exprLanguage.Hscript)
        g.setDisplayFlag(False)
    if rotary is not None:
        rotary.setExpression(f'{rotary.eval()!r} + 360 * ch("{rotary.node().relativePathTo(g)}/drive")', hou.exprLanguage.Hscript)
    return dict(control=g.path(), solver=solver.path(), drop_parm=spec["drop_parm"], drum_rotation_parm=spec["drum_rotation_parm"])


def transfer(spec):
    payload = geometry_obj(spec["payload"])
    network = payload.parent()
    if payload.input(0):
        raise ValueError("Select an unparented payload")
    channels = [p for name in ("t","r","s","p","pr","scale","xOrd","rOrd") for p in (payload.parmTuple(name) or ()) if p.keyframes()]
    if channels and not spec["replace_motion"]:
        raise ValueError("Set replace_motion to take over the payload's animated transform in the copy")
    first = spec["stages"][0]["frame"]
    hou.setFrame(first)
    neutral = payload.worldTransform()
    values = [(p, p.eval()) for p in channels]
    blend = network.createNode("blend", "SUPPORT_" + payload.name())
    blend.parm("blendtype1").set(1)  # Sequence: exactly one input owns the pose.
    blend.setDisplayFlag(False)
    poses = []
    events = []
    for i, stage in enumerate(spec["stages"]):
        support = hou.node(stage["support"])
        if not isinstance(support, hou.ObjNode) or support.parent() != network or support == payload or payload in support.inputAncestors():
            raise ValueError("Support and payload must be distinct sibling objects without a dependency cycle")
        hou.setFrame(stage["frame"])
        prior = poses[-1].worldTransform() if poses else neutral
        anchor = hou.Vector3(stage["payload_anchor"]) * prior
        socket = hou.Vector3(stage["support_anchor"]) * support.worldTransform()
        error = (anchor - socket).length()
        if error > spec["tolerance"]:
            raise ValueError(f"Support {support.name()} is not seated at frame {stage['frame']}: distance {error:.8g}")
        carrier = network.createNode("null", "SOCKET_" + support.name())
        carrier.setInput(0, support)
        carrier.setPreTransform(prior * carrier.parentAndSubnetTransform().inverted())
        carrier.setDisplayFlag(False)
        carrier.moveToGoodPosition()
        poses.append(carrier)
        blend.setInput(i, carrier)
        events.append(dict(frame=stage["frame"], support=support.path(), carrier=carrier.path(), seat_error=error))
    keys = []
    for i, e in enumerate(events):
        key = hou.Keyframe()
        key.setFrame(e["frame"])
        key.setValue(i)
        key.setExpression("constant()", hou.exprLanguage.Hscript)
        keys.append(key)
    blend.parm("sequence_seq").setKeyframes(keys)
    hou.setFrame(first)
    for p, value in values:
        p.deleteAllKeyframes()
        p.set(value, follow_parm_reference=False)
    payload.setInput(0, blend)
    payload.setWorldTransform(neutral, fail_on_locked_parms=True)
    blend.moveToGoodPosition()
    return dict(control=blend.path(), payload=payload.path(), events=events)


def build(req):
    spec = req["spec"]
    hou.setFrame(req["frame"])
    result = {"fourbar": fourbar, "reeving": reeving, "transfer": transfer}[spec["kind"]](spec)
    hou.setFrame(req["frame"])
    hou.hipFile.save(req["file"], save_to_recent_files=False)
    hou.hipFile.load(req["file"], suppress_save_prompt=True)
    if spec["kind"] == "transfer":
        payload = hou.node(result["payload"])
        for i, event in enumerate(result["events"]):
            hou.setFrame(event["frame"])
            world = hou.node(event["carrier"]).worldTransform()
            if not payload.worldTransform().isAlmostEqual(world, 1e-6):
                raise RuntimeError(f"Saved payload does not follow selected support at {event['frame']}")
            if i and not world.isAlmostEqual(hou.node(result["events"][i-1]["carrier"]).worldTransform(), 1e-6):
                raise RuntimeError(f"Support switch changes pose at {event['frame']}")
    else:
        for frame, drive in spec["keys"]:
            hou.setFrame(frame)
            checked_geo(result["solver"])
            if abs(hou.node(result["control"]).evalParm("drive") - drive) > 1e-5:
                raise RuntimeError(f"Drive did not replay at frame {frame}")
    return {"kind": spec["kind"], "verified_after_reopen": True, **result}
