"""Probe SOP parameters and output in the current Houdini scene; all edits are temporary."""
import hashlib
import json
import math
import os
from pathlib import Path

import hou
import hjson

from .gap_records import experiment_capability, experiment_gap
from .sop_worker import numeric
from .storage import home, record, sha, uid


def _sop(path):
    result = hou.node(path)
    if not isinstance(result, hou.SopNode):
        raise ValueError(f"Choose an existing SOP node: {path}")
    return result


def _metrics(sop):
    geo = sop.geometry()
    if geo is None or sop.errors():
        raise ValueError(f"{sop.path()}: {sop.errors() or 'geometry unavailable'}")
    positions = geo.pointFloatAttribValuesAsString("P")
    digest = hashlib.sha256(positions)
    cd = geo.findPointAttrib("Cd")
    if cd is not None and cd.dataType() == hou.attribData.Float:
        digest.update(geo.pointFloatAttribValuesAsString("Cd"))
    points = geo.intrinsicValue("pointcount")
    prims = geo.intrinsicValue("primitivecount")
    measured = {"points":points, "primitives":prims, "vertices":geo.intrinsicValue("vertexcount"),
                "positions_sha256":hashlib.sha256(positions).hexdigest(), "output_sha256":digest.hexdigest()}
    # A mesh can change connectivity, another attribute or a packed transform while P and Cd remain identical.
    # The native geometry stream also carries the time/host of serialisation in its geometry header.
    payload = hjson.loads(geo.data())
    _remove_write_info(payload, {})
    measured["geometry_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if points or prims:
        bbox = geo.boundingBox()
        measured.update(bbox_min=list(bbox.minvec()), bbox_max=list(bbox.maxvec()))
    return measured


def _remove_write_info(value, embedded):
    if isinstance(value, dict):
        reference = value.get("embedded")
        if isinstance(reference, str) and reference.startswith("embed:"):
            value["embedded"] = embedded.setdefault(reference, len(embedded))
        children = value.values()
    elif isinstance(value, list):
        if value[:1] == ["fileversion"]:
            for i in reversed(range(2, len(value)-1, 2)):
                if value[i] in ("info", "index"):
                    del value[i:i+2]
        elif value[:1] == ["gu:embeddedgeo"] and len(value) > 1 and isinstance(value[1], str):
            value[1] = embedded.setdefault(value[1], len(embedded))
        children = value
    else:
        return
    for child in children:
        if isinstance(child, (dict, list)):
            _remove_write_info(child, embedded)


def _variants(action, control, values, variants, changes):
    if action == "sweep":
        if variants or changes or not control or not 2 <= len(values) <= 7 or len(set(values)) != len(values):
            raise ValueError("Supply one control and 2 to 7 distinct sweep values")
        return [(str(i), {control:value}) for i,value in enumerate(values)]
    if action == "compare":
        if values or changes or control or not 2 <= len(variants) <= 7:
            raise ValueError("Supply 2 to 7 named parameter variants to compare")
        if any(not label.strip() for label in variants):
            raise ValueError("Each variant needs a nonempty label")
        return list(variants.items())
    if action == "motion" and not (values or variants or control):
        return [("motion", changes)]
    raise ValueError("Use sweep, compare or motion with the corresponding arguments")


def _write_controls(parms, values):
    for name,value in values.items():
        parm = parms[name]
        if parm.eval() != value:
            parm.set(int(value) if isinstance(parm.parmTemplate(), (hou.IntParmTemplate,hou.ToggleParmTemplate))
                     else value, follow_parm_reference=False)
        if not math.isclose(parm.eval(), value, abs_tol=1e-7, rel_tol=1e-7):
            raise ValueError(f"Control did not take the requested value: {parm.path()}")


def run(action, node, control="", values=None, frame=1, witness="", variants=None, frames=None,
        capture=False, camera="", topic="", prediction="", expect_change=None, changes=None):
    """Run on Houdini's GUI thread. The optional witness defaults to the controlled SOP."""
    capture_fn = None
    if capture:
        from .scene import capture_view
        capture_fn = capture_view
    return _study(action, node, control, values, frame, witness, variants, frames, capture_fn, camera,
                  topic, prediction, expect_change, changes, "live", {})


def study_file(req, process):
    """Measure an already-loaded HIP. Optical samples use its Mantra ROP, independent of any UI."""
    opts = req["study"]
    capture_fn = None
    if opts["renderer"]:
        rop = hou.node(opts["renderer"])
        if not isinstance(rop, hou.RopNode) or rop.type().name() != "ifd":
            raise ValueError("For saved optical evidence choose an existing Mantra ROP")
        camera = opts["camera"]
        if camera:
            cam = hou.node(camera)
            if not isinstance(cam, hou.ObjNode) or cam.type().name() != "cam":
                raise ValueError("Choose an existing camera OBJ")
            rop.parm("camera").set(cam.path(), follow_parm_reference=False)
        rop.parm("soho_foreground").set(1, follow_parm_reference=False)

        def capture_fn(f, _, metrics_fn):
            key = uid()
            path = home() / "images" / (key+".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                rop.render(frame_range=(f, f), output_file=str(path))
                with path.open("rb") as stream:
                    if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                        raise RuntimeError("Mantra did not produce a PNG")
                return dict(image_id=key, sha256=sha(path), frame=f, camera=rop.evalParm("camera"),
                            renderer=rop.path(), metrics=metrics_fn())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
    return _study(opts["action"], opts["node"], opts["control"], opts["values"], opts["frame"],
                  opts["witness"], opts["variants"], opts["frames"], capture_fn, opts["camera"],
                  opts["topic"], opts["prediction"], opts["expect_change"], opts["changes"], process,
                  {"hip":req["hip"], "hip_sha256":sha(Path(req["hip"]))})


def _study(action, node, control, values, frame, witness, variants, frames, capture_fn, camera,
           topic, prediction, expect_change, changes, process, source):
    target = _sop(node)
    output = _sop(witness) if witness else target
    plans = _variants(action, control, values or [], variants or {}, changes or {})
    at = [frame] if frames is None else frames
    if (not at or any(type(f) is not int for f in at) or len(at)*len(plans)>48 or
            (action=="sweep" and len(at)!=1) or (action=="motion" and (len(at)<2 or at!=sorted(set(at))))):
        raise ValueError("Use one sweep frame or at most 48 total samples; motion needs increasing frames")
    requested = {}
    for _,entries in plans:
        for name,value in entries.items():
            if not name or "/" in name or type(value) not in (int,float):
                raise ValueError("Use parameter names on the selected SOP and finite numeric values")
            requested.setdefault(name, []).append(value)
    target.updateParmStates()
    parms = {key:numeric(target,key,vals,allow_toggle=True) for key,vals in requested.items()}
    for parm in parms.values():
        if parm.isMultiParmParent() or parm.parmTemplate().scriptCallback():
            raise ValueError(f"Choose a scalar without a parameter callback or multiparm side effects: {parm.path()}")

    original_frame = hou.frame()
    original = {key:p.eval() for key,p in parms.items()}
    baseline = {"version":hou.applicationVersionString(), "node_type":target.type().nameWithCategory(),
                "node":target.path(), "witness":output.path(), "frame":original_frame,
                "parameters":original, "metrics":_metrics(output)}
    candidates = {}
    new_images = []
    try:
        try:
            for label, edits in plans:
                _write_controls(parms, {**original, **edits})
                actual = {key:p.eval() for key,p in parms.items()}
                samples = []
                for f in at:
                    hou.setFrame(f)
                    measurement = _metrics(output)
                    sample = {"frame":f, "metrics":measurement}
                    if capture_fn:
                        image = capture_fn(f, camera, lambda: measurement)
                        new_images.append(image["image_id"])
                        from PIL import Image
                        with Image.open(home()/"images"/(image["image_id"]+".png")) as picture:
                            image["pixel_sha256"] = hashlib.sha256(picture.convert("RGBA").tobytes()).hexdigest()
                        sample.update(image)
                    if action == "sweep":
                        sample["actual"] = actual[control]
                    samples.append(sample)
                candidates[label] = {"parameters":actual, "samples":samples}
        finally:
            try:
                _write_controls(parms, original)
            finally:
                hou.setFrame(original_frame)
            if _metrics(output) != baseline["metrics"]:
                raise RuntimeError("Restored controls did not reproduce the original witness geometry")
    except BaseException:
        for image_id in new_images:
            (home()/"images"/(image_id+".png")).unlink(missing_ok=True)
        raise

    flat = [sample for candidate in candidates.values() for sample in candidate["samples"]]
    # Compare variants at the same frame; normal animation across frames is not a variant difference.
    groups = [flat] if action=="motion" else list(zip(*(v["samples"] for v in candidates.values())))
    def differs(key):
        return any(sample[key] != group[0][key] for group in groups for sample in group[1:])
    geometry_change = differs("metrics")
    pixel_change = differs("pixel_sha256") if capture_fn else None
    changed = geometry_change or bool(pixel_change)
    info = dict(baseline=baseline, baseline_restored=True, observed_change=changed, process=process, **source,
                observed_geometry_change=geometry_change, observed_pixel_change=pixel_change, process_pid=os.getpid(),
                metric_scope="serialized SOP geometry (excluding writer info); output_sha256 is P/float Cd; optional RGBA pixels",
                prediction=prediction, expect_change=expect_change)
    if action == "compare":
        info["candidates"] = candidates
    else:
        info["samples"] = flat
    if action == "sweep":
        info["control"] = control
    mismatch = (expect_change is not None and changed != expect_change) or (expect_change is None and action=="sweep" and not changed)
    if capture_fn or topic.strip() or mismatch:
        scope = "saved" if source else "live"
        tags = [topic.strip().lower() or scope+"-study", target.type().name().lower()]
        label = control if action=="sweep" else action
        if mismatch:
            info["gap_capability"] = experiment_capability(baseline["node_type"], label, expect_change)
        card = record({"sweep":"experiment","compare":"comparison","motion":"motion"}[action],
                      f"{baseline['node_type']} / {label}", tags, f"{len(flat)} {scope} samples at {output.path()}.", info)
        if mismatch:
            card.update(experiment_gap(card, info["gap_capability"], at[0],
                        values if action=="sweep" else at if action=="motion" else list(candidates),
                        expect_change, changed, prediction))
        return {**info, **card}
    return info
