"""Reproducible capability gaps and proposed changes in the local research library."""
import hashlib
import json
import tempfile
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .storage import details, home, ident, read, search, write


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


def fingerprint(*values):
    value = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf8")).hexdigest()[:32]


def once(key, kind, title, topics, summary, data, parent, status):
    directory = home() / "records"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    card = dict(id=key, kind=kind, title=title, topics=topics, summary=summary, parent=parent, status=status)
    if not target.exists():
        # Publish the pair together. Concurrent clients can both observe the same limitation.
        with tempfile.TemporaryDirectory(dir=directory.parent) as temp:
            staged = Path(temp) / "record"
            write(staged / "details.json", data)
            write(staged / "card.json", card)
            try:
                staged.rename(target)
                return card, True
            except OSError:
                if not (target / "card.json").is_file():
                    raise
    return read(target / "card.json"), False


def evidence_ids(ids):
    return sorted({details(ident(key))["id"] for key in ids})


def resolution(gap):
    offset = 0
    while True:
        page = search(kind="gap", status="resolved", limit=20, offset=offset)
        for card in page["cards"]:
            if gap in details(card["id"])["details"].get("sources", []):
                return card["id"]
        offset = page["next_offset"]
        if offset is None:
            return None


def report(entry, replay=None):
    sources = evidence_ids(entry.sources)
    capability = " ".join(unicodedata.normalize("NFKC", entry.capability).casefold().split())
    gap = fingerprint("capability-gap/v1", capability)
    data = dict(signal=entry.signal, expected=entry.expected, observed=entry.observed,
                reproduce=entry.reproduce, sources=sources)
    if replay is not None:
        data["replay"] = replay
    observation = fingerprint("gap-observation/v1", gap, data)
    topic = [entry.topic.casefold()]
    once(observation, "gap_observation", capability, topic, entry.observed, data, gap, "observed")
    card, created = once(gap, "gap", capability, topic, entry.expected,
                         {"capability": capability, "sources": [observation]}, None, "open")
    return {"gap": card["id"], "observation": observation, "created": created,
            "prior_resolution": resolution(gap),
            "next": "Call improvement with request.action='propose', gap, change, acceptance, and this observation in sources."}


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
