"""Typed input specifications for mechanical constraint rigs."""
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from .mechanical_rig import save_variant
from .mechanism_math import check_fourbar_sweep


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FourBar(Spec):
    kind: Literal["fourbar"]
    network: str = "/obj"
    ground_a: tuple[float, float]
    ground_d: tuple[float, float]
    crank: float = Field(gt=0)
    coupler: float = Field(gt=0)
    rocker: float = Field(gt=0)
    branch: Literal["left", "right"] = "left"
    z: float = 0
    keys: list[tuple[int, float]] = Field(min_length=1, description="Frame, crank angle from local +X, in degrees.")
    parts: tuple[str, str, str] | None = Field(default=None, description="Optional unparented static crank, coupler and rocker geometry OBJs in this XY network, modelled at the first angle.")


class Reeving(Spec):
    kind: Literal["reeving"]
    network: str = "/obj"
    falls: Literal[2, 4]
    drum_radius: float = Field(gt=0)
    sheave_radius: float = Field(gt=0)
    initial_drop: float = Field(gt=0)
    keys: list[tuple[int, float]] = Field(min_length=1, description="Frame, drum revolutions. Positive reels in rope. Zero corresponds to initial_drop.")
    drop_parm: str = Field(default="", description="Optional existing static hook-drop parameter on a model already threaded for the selected number of falls.")
    drum_rotation_parm: str = Field(default="", description="Optional static rotation channel at the drum axle, in degrees; positive turns add 360 degrees.")


class Support(Spec):
    frame: int
    support: str
    payload_anchor: tuple[float, float, float]
    support_anchor: tuple[float, float, float]


class Transfer(Spec):
    kind: Literal["transfer"]
    payload: str
    stages: list[Support] = Field(min_length=2)
    tolerance: float = Field(gt=0, default=0.001)
    replace_motion: bool = False


def run(hip, spec, output, topic):
    from .storage import record, sha
    data = spec.model_dump()
    frames = [k[0] for k in spec.keys] if not isinstance(spec, Transfer) else [s.frame for s in spec.stages]
    if any(a >= b for a, b in zip(frames, frames[1:])):
        raise ValueError("Frames must be strictly increasing")
    if isinstance(spec, FourBar):
        check_fourbar_sweep(data)
    result = save_variant(hip, output, spec.kind, dict(action="mechanism", spec=data, frame=frames[0]))
    if topic.strip():
        card = record("mechanism", spec.kind, [topic.strip().lower()], f"Reopened and verified {spec.kind} constraint",
                      {**result, "spec": data, "hip_sha256": sha(Path(result["hip"]))})
        result["evidence_id"] = card["id"]
    return result
