"""Directional clearance between two pieces of animated geometry in a saved HIP."""
import math
import tempfile
from pathlib import Path


def check_range(start, end, axis, minimum, maximum):
    if axis not in ("x", "y", "z"):
        raise ValueError("Choose the world axis x, y or z")
    if not 1 <= end - start + 1 <= 4096:
        raise ValueError("Choose an inclusive range of 1 to 4096 integer frames")
    if any(v is not None and not math.isfinite(v) for v in (minimum, maximum)):
        raise ValueError("Limits must be finite scene-unit distances")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum must be <= maximum")


def summarize(samples, minimum, maximum):
    lowest = highest = first_violation = first_missing = None
    measured = missing = violations = 0
    for frame, gap, reason in samples:
        if gap is None:
            missing += 1
            if first_missing is None:
                first_missing = {"frame": frame, "reason": reason}
            continue
        measured += 1
        witness = {"frame": frame, "gap": gap}
        if lowest is None or gap < lowest["gap"]:
            lowest = witness
        if highest is None or gap > highest["gap"]:
            highest = witness
        if (minimum is not None and gap < minimum) or (maximum is not None and gap > maximum):
            violations += 1
            if first_violation is None:
                first_violation = witness
    status = "measured" if minimum is None and maximum is None else "passed"
    if violations:
        status = "failed"
    elif missing:
        status = "incomplete"
    return dict(status=status, measured_frames=measured, missing_frames=missing,
                violating_frames=violations, lowest=lowest, highest=highest,
                first_violation=first_violation, first_missing=first_missing)


def geometry_source(hou, path):
    node = hou.node(path)
    if not path.startswith("/obj/") or node is None:
        raise ValueError(f"Select an existing geometry OBJ or SOP under /obj: {path}")
    if isinstance(node, hou.ObjNode) and isinstance(node.displayNode(), hou.SopNode):
        return node, node
    if not isinstance(node, hou.SopNode):
        raise ValueError(f"Select a geometry OBJ or SOP: {path}")
    owner = node.parent()
    while owner is not None and not isinstance(owner, hou.ObjNode):
        owner = owner.parent()
    if owner is None:
        raise ValueError(f"No geometry object owns {path}")
    return node, owner


def axis_bounds(hou, source, axis):
    node, owner = source
    sop = node if isinstance(node, hou.SopNode) else owner.displayNode()
    if not isinstance(sop, hou.SopNode):
        raise ValueError(f"{node.path()}: no display SOP")
    geo = sop.geometry()
    if sop.errors() or geo is None:
        raise ValueError(f"{sop.path()}: {sop.errors() or 'geometry unavailable'}")
    if not (geo.intrinsicValue("pointcount") or geo.intrinsicValue("primitivecount")):
        raise ValueError(f"{sop.path()}: empty geometry")
    bounds = geo.boundingBox(owner.worldTransform())
    low, high = bounds.minvec()[axis], bounds.maxvec()[axis]
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise ValueError(f"{sop.path()}: invalid bounds")
    return low, high


def measure_frames(req):
    import hou

    upper = geometry_source(hou, req["upper"])
    lower = geometry_source(hou, req["lower"])
    axis = "xyz".index(req["axis"])

    def samples():
        for frame in range(req["start"], req["end"] + 1):
            hou.setFrame(frame)
            try:
                gap = axis_bounds(hou, upper, axis)[0] - axis_bounds(hou, lower, axis)[1]
            except (hou.Error, ValueError) as exc:
                yield frame, None, str(exc)
            else:
                yield frame, gap, None

    entering_frame = hou.frame()
    try:
        return {"fps": hou.fps(), **summarize(samples(), req["minimum"], req["maximum"])}
    finally:
        hou.setFrame(entering_frame)


def run(hip, upper, lower, start, end, axis, minimum, maximum, topic):
    from .sop_lab import hip_path, worker
    from .storage import record, sha

    check_range(start, end, axis, minimum, maximum)
    file = hip_path(hip)
    query = dict(hip=str(file), upper=upper, lower=lower, start=start, end=end,
                 axis=axis, minimum=minimum, maximum=maximum)
    with tempfile.TemporaryDirectory(prefix="houdini-gap-") as folder:
        result = worker({"action": "animation_gap", **query}, Path(folder))
    report = {**query, "units": "scene units", "metric": "world-axis bounds gap", **result}
    if topic.strip():
        card = record("animation_gap", f"{upper.rsplit('/', 1)[-1]} / {lower.rsplit('/', 1)[-1]}",
                      [topic.strip().lower()], f"World {axis} bounds gap, frames {start}–{end}: {result['status']}",
                      {**report, "hip_sha256": sha(file)})
        report["evidence_id"] = card["id"]
    return report
