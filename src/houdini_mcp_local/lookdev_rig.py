"""Owned, reversible product-lighting rigs. No existing scene lights are changed.

Coordinates are metres, Y up, local -Z aims at target. Defaults are exploratory
positions for the current assembly, not calibrated exposure or automatic framing.
The public entrypoint is operate(action, name='product', settings=None).
"""
from copy import deepcopy
import hashlib
import json
import math
import re

OWNER = "workai.lookdev_rig.v1"
OWNER_KEY = "workai_lookdev_owner"
LIGHT_IDS = ("key", "fill", "rim")
CAMERA_IDS = ("hero", "reference", "detail")
POSE = {"position", "target", "up"}
LIGHT_KEYS = POSE | {"size", "intensity", "exposure", "color", "enabled"}
CAMERA_KEYS = POSE | {"focal_mm", "aperture_mm", "resolution"}
TRANSFORM_PARMS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
LIGHT_PARMS = ("light_type", "areasize1", "areasize2", "light_intensity",
               "light_exposure", "light_colorr", "light_colorg", "light_colorb", "light_enable")
CAMERA_PARMS = ("projection", "focal", "aperture", "resx", "resy")


def default_settings():
    def light(position, target, size, intensity):
        return dict(position=position, target=target, size=size, intensity=intensity,
                    exposure=0.0, color=[1.0, 1.0, 1.0], enabled=True)
    def camera(position, target, focal, resolution):
        return dict(position=position, target=target, focal_mm=focal,
                    aperture_mm=36.0, resolution=resolution)
    return {"lights": {
        "key": light([-1.2, 2.6, .9], [0, .35, 0], [3.4, 1.2], 2.0),
        "fill": light([-.8, -1.2, -2.4], [0, .18, 0], [3.2, 1.8], 1.0),
        "rim": light([.3, 1.4, 2.3], [0, .35, 0], [3.0, .25], 1.0)},
        "cameras": {
        "hero": camera([4.2, 2.4, -5.8], [0, .35, 0], 65, [1200, 675]),
        "reference": camera([3, -5.13, -5.1], [0, .37, 0], 75, [810, 1080]),
        "detail": camera([1.62, .72, 2.6], [.12, .184, .5], 100, [1200, 800])}}


def _number(value, label, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(label + " is outside supported bounds")
    return float(value)


def _vector(value, length, label, low=None, high=None):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(label + " must have " + str(length) + " components")
    return [_number(v, label, low, high) for v in value]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(v):
    length = math.sqrt(_dot(v, v))
    if length < 1e-8:
        raise ValueError("Degenerate camera/light orientation")
    return [x / length for x in v]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def orientation_matrix(spec, is_light):
    """Row-major Houdini matrix; light long edge follows projected world X."""
    eye = spec["position"]
    z = _unit([a-b for a, b in zip(eye, spec["target"])])
    if "up" in spec:
        x = _unit(_cross(spec["up"], z))
    elif is_light:
        x = _unit([1.0-z[0]*z[0], -z[0]*z[1], -z[0]*z[2]])
    else:
        x = _unit(_cross([0, 1, 0], z))
    y = _cross(z, x)
    return [*x, 0.0, *y, 0.0, *z, 0.0, *eye, 1.0]


def validate_settings(settings):
    """Validate a complete declarative rig; does not import hou or mutate scene."""
    if not isinstance(settings, dict) or set(settings) != {"lights", "cameras"}:
        raise ValueError("Settings must contain exactly lights and cameras")
    result = deepcopy(settings)
    for group, ids, keys in (("lights", LIGHT_IDS, LIGHT_KEYS), ("cameras", CAMERA_IDS, CAMERA_KEYS)):
        entries = result[group]
        if not isinstance(entries, dict) or set(entries) != set(ids):
            raise ValueError(group + " must contain exactly " + str(ids))
        for name, spec in entries.items():
            required = keys - {"up"}
            if not isinstance(spec, dict) or set(spec) - keys or required - set(spec):
                raise ValueError("Invalid fields for " + group + "/" + name)
            for field in POSE & set(spec):
                spec[field] = _vector(spec[field], 3, field, -1e6, 1e6)
            if group == "lights":
                spec["size"] = _vector(spec["size"], 2, "size", 1e-5, 1e4)
                spec["color"] = _vector(spec["color"], 3, "color", 0, 1)
                spec["intensity"] = _number(spec["intensity"], "intensity", 0, 1e6)
                spec["exposure"] = _number(spec["exposure"], "exposure", -30, 30)
                if type(spec["enabled"]) is not bool:
                    raise ValueError("enabled must be a boolean")
            else:
                spec["focal_mm"] = _number(spec["focal_mm"], "focal_mm", 1, 2000)
                spec["aperture_mm"] = _number(spec["aperture_mm"], "aperture_mm", 1, 200)
                resolution = _vector(spec["resolution"], 2, "resolution", 1, 16384)
                if any(int(v) != v for v in resolution):
                    raise ValueError("resolution must contain integers")
                spec["resolution"] = [int(v) for v in resolution]
            orientation_matrix(spec, group == "lights")
    return result


def merge_settings(base, patch):
    if not isinstance(patch, dict) or set(patch) - {"lights", "cameras"}:
        raise ValueError("Unknown rig settings group")
    result = deepcopy(base)
    for group, entries in patch.items():
        if not isinstance(entries, dict) or set(entries) - set(result[group]):
            raise ValueError("Unknown rig member")
        allowed = LIGHT_KEYS if group == "lights" else CAMERA_KEYS
        for name, changes in entries.items():
            if not isinstance(changes, dict) or set(changes) - allowed:
                raise ValueError("Unknown rig member field")
            # A new pose defaults again to world Y / projected world X. An explicit
            # up vector from capture reproduces the captured orientation instead.
            if {"position", "target"} & set(changes) and "up" not in changes:
                result[group][name].pop("up", None)
            result[group][name].update(deepcopy(changes))
    return validate_settings(result)


def _hou():
    import hou
    return hou


def _path(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", name):
        raise ValueError("Rig name must be 1-48 ASCII letters/digits/underscores, starting with a letter")
    return "/obj/workai_lookdev_" + name


def _controls(node, light):
    # Native cameras have SideFX's default lock(1) expressions on scale.
    # Preserve these rather than treating them as editable scalar channels.
    return (TRANSFORM_PARMS + LIGHT_PARMS) if light else (TRANSFORM_PARMS[:6] + CAMERA_PARMS)


def _managed(name):
    root = _hou().node(_path(name))
    if root is None:
        return None
    if root.type().name() != "subnet" or root.userData(OWNER_KEY) != OWNER:
        raise ValueError("Rig path is occupied by an unowned node; no changes")
    expected = set(LIGHT_IDS + CAMERA_IDS)
    if {n.name() for n in root.children()} != expected:
        raise ValueError("Rig membership changed; no changes")
    for node in root.children():
        light = node.name() in LIGHT_IDS
        if node.userData(OWNER_KEY) != OWNER or node.userData("workai_lookdev_role") != node.name():
            raise ValueError("Rig child ownership changed; no changes")
        expected_type = "hlight" if light else "cam"
        if node.type().name().split("::")[0] != expected_type:
            raise ValueError("Unexpected rig child type")
    return root


def _state(root):
    if root is None:
        return {"exists": False}
    # Include all channels, expressions, wiring, flags, userdata and internal
    # nodes, not only fields controlled by the tool, in the conflict fingerprint.
    nodes = []
    for node in sorted((root, *root.allSubChildren()), key=lambda n: n.path()):
        flags = {}
        for method in ("isDisplayFlagSet", "isRenderFlagSet", "isBypassed", "isHardLocked"):
            if hasattr(node, method):
                flags[method] = getattr(node, method)()
        nodes.append({"path": node.path(), "type": node.type().name(),
                      "parms": {p.name(): [p.rawValue(), [k.asCode() for k in p.keyframes()]] for p in node.parms()},
                      "inputs": [n.path() if n else None for n in node.inputs()],
                      "outputs": sorted(n.path() for n in node.outputs()),
                      # Houdini adds its save-version marker on reopen.
                      "userdata": {k: v for k, v in node.userDataDict().items() if k != "___Version___"},
                      "flags": flags})
    return {"exists": True, "nodes": nodes}


def _fingerprint(root):
    return hashlib.sha256(json.dumps(_state(root), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_settings(root):
    result = {"lights": {}, "cameras": {}}
    for node in root.children():
        light = node.name() in LIGHT_IDS
        m = list(node.worldTransform().asTuple())
        spec = dict(position=m[12:15], target=[m[12+i]-m[8+i] for i in range(3)], up=m[4:7])
        if light:
            spec.update(size=list(node.parmTuple("areasize").eval()), intensity=node.evalParm("light_intensity"),
                        exposure=node.evalParm("light_exposure"), color=list(node.parmTuple("light_color").eval()),
                        enabled=bool(node.evalParm("light_enable")))
        else:
            spec.update(focal_mm=node.evalParm("focal"), aperture_mm=node.evalParm("aperture"),
                        resolution=[node.evalParm("resx"), node.evalParm("resy")])
        result["lights" if light else "cameras"][node.name()] = spec
    return result


def _snapshot(root):
    if root is None:
        return {"exists": False}
    return {"exists": True, "values": {n.name(): {p: n.evalParm(p) for p in _controls(n, n.name() in LIGHT_IDS)}
                                        for n in root.children()}}


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or type(snapshot.get("exists")) is not bool:
        raise ValueError("Invalid restore snapshot")
    if not snapshot["exists"]:
        if set(snapshot) != {"exists"}:
            raise ValueError("Unexpected absent snapshot data")
        return
    if set(snapshot) != {"exists", "values"} or not isinstance(snapshot["values"], dict):
        raise ValueError("Invalid restore values")
    if set(snapshot["values"]) != set(LIGHT_IDS + CAMERA_IDS):
        raise ValueError("Invalid restore membership")
    for name, values in snapshot["values"].items():
        required = set(_controls(None, name in LIGHT_IDS))
        if not isinstance(values, dict) or set(values) != required:
            raise ValueError("Invalid restore parameter set")
        for key, value in values.items():
            _number(value, key, -1e12, 1e12)


def _restore_values(root, snapshot):
    if not snapshot["exists"]:
        root.destroy()
    else:
        for name, values in snapshot["values"].items():
            root.node(name).setParms(values)


def _preflight_root(root):
    if root is None:
        return
    identity = _hou().Matrix4(1)
    if root.worldTransform() != identity or any(root.inputs()):
        raise ValueError("Rig root must retain identity transform and no input parenting")
    for node in root.children():
        if any(node.inputs()) or node.evalParm("lookatpath") or node.evalParm("constraints_on"):
            raise ValueError("Rig children must not have external parenting, constraints or look-at links")
        if node.name() in LIGHT_IDS and node.evalParm("light_type") != 2:
            raise ValueError("Managed rig light is no longer a rectangular area light")
        if node.name() in CAMERA_IDS and node.evalParm("projection") != 0:
            raise ValueError("Managed rig camera is no longer perspective")
        for name in _controls(node, node.name() in LIGHT_IDS):
            if node.parm(name).keyframes() or node.parm(name).isLocked():
                raise ValueError("Animated, expression-driven or locked controlled channels require manual handling")


def _apply_values(root, settings, changes=None):
    hou = _hou()
    for group, entries in settings.items():
        for name, spec in entries.items():
            changed_fields = None if changes is None else changes.get(group, {}).get(name)
            if changes is not None and not changed_fields:
                continue
            node = root.node(name)
            light = group == "lights"
            if changed_fields is None or POSE & set(changed_fields):
                node.setWorldTransform(hou.Matrix4(orientation_matrix(spec, light)))
            if light:
                node.setParms({"light_type": 2, "areasize1": spec["size"][0], "areasize2": spec["size"][1],
                               "light_intensity": spec["intensity"], "light_exposure": spec["exposure"],
                               "light_colorr": spec["color"][0], "light_colorg": spec["color"][1],
                               "light_colorb": spec["color"][2], "light_enable": int(spec["enabled"])})
            else:
                node.setParms({"projection": 0, "focal": spec["focal_mm"], "aperture": spec["aperture_mm"],
                               "resx": spec["resolution"][0], "resy": spec["resolution"][1]})


def _result(root, name, action):
    return {"action": action, "name": name, "exists": root is not None, "root_path": _path(name),
            "fingerprint": _fingerprint(root), "settings": _read_settings(root) if root else None,
            "light_paths": [root.node(n).path() for n in LIGHT_IDS] if root else [],
            "camera_paths": {n: root.node(n).path() for n in CAMERA_IDS} if root else {},
            "units": "metres", "coordinate_system": "Y up; local -Z toward target",
            "saved": False, "existing_scene_lights_unchanged": True,
            "note": "Exploratory light intensities; not exposure-calibrated. Apply/restore dirties scene, never saves HIP."}


def operate(action, name="product", settings=None):
    """inspect/capture/apply/restore an owned rig; capture.settings is apply-ready.

    apply accepts partial lights/cameras settings; absent rig starts from defaults.
    restore accepts {'restore_token': token}. Tokens are JSON data, reusable after
    save/reopen while the complete current rig fingerprint still matches.
    """
    _path(name)
    if action not in {"inspect", "capture", "apply", "restore"}:
        raise ValueError("Unsupported lookdev rig action")
    if action in {"inspect", "capture"} and settings is not None:
        raise ValueError("Read-only action does not accept settings")
    root = _managed(name)
    if action in {"inspect", "capture"}:
        return _result(root, name, action)
    _preflight_root(root)
    before = _snapshot(root)
    before_fingerprint = _fingerprint(root)
    if action == "restore":
        if not isinstance(settings, dict) or set(settings) != {"restore_token"}:
            raise ValueError("restore requires restore_token")
        token = settings["restore_token"]
        required = {"schema", "name", "before_snapshot", "before_fingerprint", "after_fingerprint"}
        if not isinstance(token, dict) or set(token) != required or token["schema"] != OWNER or token["name"] != name:
            raise ValueError("Invalid restore token or wrong rig name")
        _validate_snapshot(token["before_snapshot"])
        if not token["before_snapshot"]["exists"] and token["before_fingerprint"] != _fingerprint(None):
            raise ValueError("Invalid absent-state restore fingerprint")
        if root is None or before_fingerprint != token["after_fingerprint"]:
            raise ValueError("Restore conflict: rig changed since apply; no changes")
        try:
            _restore_values(root, token["before_snapshot"])
            root = _managed(name)
            if _fingerprint(root) != token["before_fingerprint"]:
                raise RuntimeError("Restored rig fingerprint differs from original")
        except Exception:
            if root is not None:
                _restore_values(root, before)
            raise
        return _result(root, name, action)
    merged = merge_settings(_read_settings(root) if root else default_settings(), {} if settings is None else settings)
    try:
        if root is None:
            root = _hou().node("/obj").createNode("subnet", _path(name).rsplit("/", 1)[1])
            root.setUserData(OWNER_KEY, OWNER)
            for child_name in LIGHT_IDS + CAMERA_IDS:
                node = root.createNode("hlight" if child_name in LIGHT_IDS else "cam", child_name)
                node.setUserData(OWNER_KEY, OWNER)
                node.setUserData("workai_lookdev_role", child_name)
        _apply_values(root, merged, None if not before["exists"] else ({} if settings is None else settings))
        result = _result(root, name, action)
        result["restore_token"] = {"schema": OWNER, "name": name, "before_snapshot": before,
                                   "before_fingerprint": before_fingerprint, "after_fingerprint": result["fingerprint"]}
        return result
    except Exception:
        if root is not None:
            _restore_values(root, before)
        raise
