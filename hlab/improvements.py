"""Reproducible capability gaps and proposed changes in the local research library."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .gap_records import evidence_ids, fingerprint, once, resolution, save_gap
from .storage import details


class GapReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["report"]
    capability: str = Field(min_length=1, max_length=120, description="Stable capability key shared by reports of the same limitation, e.g. rig.extend-parented-obj.")
    topic: str = Field(min_length=1, max_length=48)
    signal: Literal["missing_operation", "workaround", "unexplained_result"]
    expected: str = Field(min_length=1, max_length=600)
    observed: str = Field(min_length=1, max_length=1000)
    reproduce: str = Field(min_length=1, max_length=1500, description="Scene or minimal setup, tool/step and how to observe the limitation.")
    sources: list[str] = Field(default_factory=list, max_length=12, description="Optional existing evidence IDs.")


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["propose"]
    gap: str = Field(description="Existing open gap ID, including a gap emitted by a node experiment.")
    change: str = Field(min_length=1, max_length=1000, description="Smallest useful change to the tool, skill or experiment.")
    acceptance: str = Field(min_length=1, max_length=1000, description="An observable pass/fail test on the original case.")
    sources: list[str] = Field(default_factory=list, max_length=12, description="Additional observation or evidence IDs.")


def report(entry, replay=None):
    return save_gap(entry.capability, [entry.topic.casefold()], entry.signal, entry.expected,
                    entry.observed, entry.reproduce, entry.sources, replay)


def propose(entry):
    gap = details(entry.gap)
    if gap["kind"] != "gap" or gap["status"] != "open":
        raise ValueError("Select the original open gap")
    prior_resolution = resolution(gap["id"])
    if prior_resolution:
        return {"gap": gap["id"], "status": "previously_resolved", "resolution": prior_resolution,
                "next": "Compare the current observation with the recorded retest before proposing a regression fix."}
    sources = sorted({gap["id"], *evidence_ids(entry.sources)})
    data = dict(change=entry.change, acceptance=entry.acceptance, sources=sources)
    key = fingerprint("improvement/v1", gap["id"], data)
    card, created = once(key, "improvement", gap["title"], gap["topics"], entry.change,
                         data, gap["id"], "proposed")
    return {**card, "created": created, "gap": gap["id"], "acceptance": entry.acceptance}


def native_gap(hint, request, error):
    args = {k: v for k, v in request.items() if k not in ("file", "action")}
    entry = GapReport(action="report", capability=hint["capability"], topic=hint["topic"],
                      signal="missing_operation", expected=hint["expected"], observed=error,
                      reproduce=hint["reproduce"])
    return report(entry, {"tool": request["action"], "arguments": args})
