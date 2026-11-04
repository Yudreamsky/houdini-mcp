"""Build native one-axis FK joints on sibling geometry objects in a HIP copy."""
import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .sop_lab import hip_path, worker


class Joint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    part: str = Field(description="Absolute path to a geometry OBJ. List parent parts before children.")
    parent: str = Field(default="", description="Part path of the parent joint. Empty starts a chain.")
    kind: Literal["fixed", "hinge", "slider"]
    pivot: tuple[float, float, float] = Field(description="World XYZ of the joint at the bind frame.")
    axis: Literal["x", "y", "z"] = "y"
    limits: tuple[float, float] | None = Field(default=None, description="Travel interval containing zero. Degrees for hinge, scene units for slider.")
    keys: list[tuple[int, float]] = Field(default_factory=list, description="Ordered [frame, drive] pairs, linearly interpolated.")


def validate(joints):
    if not joints:
        raise ValueError("Supply joints in parent-first order")
    seen = set()
    for j in joints:
        if not j.part.startswith("/obj/") or j.part in seen:
            raise ValueError(f"Expected a unique absolute OBJ part: {j.part}")
        if j.parent and j.parent not in seen:
            raise ValueError(f"Parent must precede child: {j.part}")
        if j.kind == "fixed" and (j.keys or j.limits):
            raise ValueError(f"Fixed joints take no drive or limits: {j.part}")
        if j.limits and not (j.limits[0] <= 0 <= j.limits[1] and j.limits[0] < j.limits[1]):
            raise ValueError(f"Limits must span the neutral pose: {j.part}")
        last = None
        for f, v in j.keys:
            if last is not None and f <= last:
                raise ValueError(f"Keys must be in strictly increasing frame order: {j.part}")
            if j.limits and not j.limits[0] <= v <= j.limits[1]:
                raise ValueError(f"Drive outside limits at frame {f}: {j.part}")
            last = f
        seen.add(j.part)


def run(hip, joints, frame, output, replace_motion):
    validate(joints)
    result = save_variant(hip, output, "rig", dict(action="mechanical_rig", frame=frame,
                          joints=[j.model_dump() for j in joints], replace_motion=replace_motion))
    return {**result, "bind_frame": frame}


def save_variant(hip, output, label, request):
    source = hip_path(hip)
    target = Path(output) if output else source.with_name(f"{source.stem}-{label}-{uuid.uuid4().hex[:8]}{source.suffix}")
    if not target.is_absolute() or target.parent.resolve() != source.parent or target.suffix.lower() != source.suffix.lower():
        raise ValueError("Choose a new absolute HIP path in the source folder with the same extension")
    if target.exists():
        raise FileExistsError(f"Output already exists: {target}")
    staging = source.with_name(f"_rig_stage_{uuid.uuid4().hex}{source.suffix}")
    try:
        with tempfile.TemporaryDirectory(prefix="houdini-rig-") as folder:
            result = worker(dict(**request, hip=str(source), file=str(staging)), Path(folder))
        # Windows rename publishes the whole verified file and refuses a competing destination.
        os.rename(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    return {"source": str(source), "hip": str(target), **result}
