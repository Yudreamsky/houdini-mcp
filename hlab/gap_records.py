"""Shared gap identity and evidence storage for external Python and Houdini Python."""
import hashlib
import json
import tempfile
import unicodedata
from pathlib import Path

from .storage import details, home, ident, read, search, write


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


def save_gap(capability, topics, signal, expected, observed, reproduce, sources, replay=None):
    sources = evidence_ids(sources)
    capability = " ".join(unicodedata.normalize("NFKC", capability).casefold().split())
    gap = fingerprint("capability-gap/v1", capability)
    data = dict(signal=signal, expected=expected, observed=observed,
                reproduce=reproduce, sources=sources)
    if replay is not None:
        data["replay"] = replay
    observation = fingerprint("gap-observation/v1", gap, data)
    once(observation, "gap_observation", capability, topics, observed, data, gap, "observed")
    card, created = once(gap, "gap", capability, topics, expected,
                         {"capability": capability, "sources": [observation, *sources]}, None, "open")
    return {"gap": card["id"], "observation": observation, "created": created,
            "prior_resolution": resolution(gap),
            "next": "Call improvement with request.action='propose', gap, change, acceptance, and this observation in sources."}


def experiment_capability(node_type, control, expected):
    reason = "no-response" if expected is None else "prediction-mismatch"
    return f"experiment.{reason}:{node_type}:{control}".casefold()


def experiment_gap(card, capability, frame, samples, expected, changed, prediction=""):
    """Record a new experimental witness, reusing the capability across clients."""
    expectation = prediction.strip() or {
        None: "Check whether the control changes the measured output.",
        True: "Expected a change in the measured output.",
        False: "Expected no change in the measured output.",
    }[expected]
    observed = "The measured output changed." if changed else "No measured output change."
    receipt = save_gap(capability, card["topics"], "unexplained_result", expectation, observed,
                       f"Repeat {card['title']} at frame {frame} with samples {samples}. "
                       "Use the linked experiment's input, baseline and witness.",
                       [card["id"]])
    return {"capability": capability, "gap": receipt["gap"], "observation": receipt["observation"],
            "prior_resolution": receipt["prior_resolution"]}
