"""Houdini-side authoring for mechanical_rig. Imported by sop_worker under hython."""
import hou


def create_drive(ctrl, joint):
    if joint["kind"] == "fixed":
        return
    rotary = joint["kind"] == "hinge"
    label = "Angle (degrees)" if rotary else "Travel (scene units)"
    limits = joint["limits"]
    options = {}
    if limits:
        options = dict(min=limits[0], max=limits[1], min_is_strict=True, max_is_strict=True)
    ctrl.addSpareParmTuple(hou.FloatParmTemplate("drive", label, 1, (0.0,), **options))
    expr = 'ch("drive")'
    if limits:
        expr = f'clamp({expr}, {limits[0]!r}, {limits[1]!r})'
    ctrl.parm(("r" if rotary else "t") + joint["axis"]).setExpression(expr, hou.exprLanguage.Hscript)


def key_drive(ctrl, pairs):
    keys = []
    for frame, value in pairs:
        key = hou.Keyframe()
        key.setFrame(frame)
        key.setValue(value)
        key.setExpression("linear()", hou.exprLanguage.Hscript)
        keys.append(key)
    if keys:
        ctrl.parm("drive").setKeyframes(keys)


def build(req):
    hou.setFrame(req["frame"])
    joints = req["joints"]
    parts = {}
    poses = {}
    animated = {}
    for joint in joints:
        path = joint["part"]
        part = hou.node(path)
        if not isinstance(part, hou.ObjNode) or not isinstance(part.displayNode(), hou.SopNode):
            raise ValueError(f"Select a geometry OBJ: {path}")
        if joint["parent"] and part.parent() != parts[joint["parent"]].parent():
            raise ValueError(f"A parent and child must share an OBJ network: {path}")
        if part.input(0) is not None:
            error = ValueError(f"Part already has a transform parent: {path} -> {part.input(0).path()}")
            error.gap_hint = dict(capability="rig.extend-parented-obj", topic="mechanical-animation",
                                  expected="Add a joint to a geometry OBJ while preserving its existing transform parent.",
                                  reproduce="Call mechanical_rig on an already-parented geometry OBJ. Replay arguments are attached.")
            raise error
        channels = [p for name in ("t", "r", "s", "p", "pr", "scale", "xOrd", "rOrd")
                    for p in (part.parmTuple(name) or ()) if p.keyframes()]
        if channels and not req["replace_motion"]:
            raise ValueError(f"{path} has animated transform channels. Set replace_motion to rebind them from the chosen frame.")
        animated[path] = [(p, p.eval()) for p in channels]
        parts[path] = part
        poses[path] = part.worldTransform()

    controls = {}
    info = []
    for joint in joints:
        path = joint["part"]
        part = parts[path]
        ctrl = part.parent().createNode("null", "JNT_" + part.name())
        if joint["parent"]:
            ctrl.setInput(0, controls[joint["parent"]])
        # All neutral joint axes start in world XYZ and then follow their parents.
        rest = hou.hmath.buildTranslate(joint["pivot"])
        ctrl.setPreTransform(rest * ctrl.parentAndSubnetTransform().inverted())
        ctrl.setDisplayFlag(False)
        ctrl.setPosition(part.position() + hou.Vector2(-1.3, 1.0))
        create_drive(ctrl, joint)
        for parm, value in animated[path]:
            parm.deleteAllKeyframes()
            parm.set(value, follow_parm_reference=False)
        part.setInput(0, ctrl)
        part.setWorldTransform(poses[path], fail_on_locked_parms=True)
        if not part.worldTransform().isAlmostEqual(poses[path], 1e-6):
            raise ValueError(f"Unable to preserve neutral world transform for {path}")
        controls[path] = ctrl
        info.append(dict(part=path, control=ctrl.path(), parent=joint["parent"], kind=joint["kind"],
                         axis=joint["axis"], pivot=joint["pivot"], limits=joint["limits"],
                         key_count=len(joint["keys"]), replaced_channels=[p.name() for p, _ in animated[path]]))
    for joint in joints:
        key_drive(controls[joint["part"]], joint["keys"])
    for path, ctrl in controls.items():
        if ctrl.parm("drive") and abs(ctrl.parm("drive").eval()) > 1e-7:
            raise ValueError(f"Drive must evaluate to zero at the bind frame: {path}")
    hou.hipFile.save(req["file"], save_to_recent_files=False)
    hou.hipFile.load(req["file"], suppress_save_prompt=True)
    hou.setFrame(req["frame"])
    by_part = {it["part"]: it["control"] for it in info}
    for it in info:
        obj, ctrl = hou.node(it["part"]), hou.node(it["control"])
        parent = hou.node(by_part[it["parent"]]) if it["parent"] else None
        if obj.input(0) != ctrl or ctrl.input(0) != parent or not obj.worldTransform().isAlmostEqual(poses[it["part"]], 1e-6):
            raise RuntimeError(f"Saved rig failed bind-pose or parent verification: {it['part']}")
    return {"joints": info, "verified_after_reopen": True}
