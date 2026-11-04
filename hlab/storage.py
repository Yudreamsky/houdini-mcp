import hashlib
import json
import os
import re
import uuid
from pathlib import Path


def home():
    fallback = Path.home() / ".houdini-research"
    return Path(os.environ.get("HOUDINI_RESEARCH_HOME", fallback)).resolve()


def uid():
    return uuid.uuid4().hex


def ident(value):
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{32}", value):
        raise ValueError("Invalid record id")
    return value


def example():
    return Path(__file__).resolve().parents[1] / "examples" / "fireworks" / "library"


def stored(*parts):
    local = home().joinpath(*parts)
    return local if local.exists() else example().joinpath(*parts)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uid() + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(kind, title, topics, summary, details, parent=None, status="observed"):
    key = uid()
    path = home() / "records" / key
    card = dict(id=key, kind=kind, title=title, topics=topics, summary=summary, status=status, parent=parent)
    write(path / "details.json", details)
    write(path / "card.json", card)
    return card


def details(key):
    folder = stored("records", ident(key))
    card = read(folder / "card.json")
    return {**card, "details": read(folder / "details.json")}


def search(topic="", kind="", limit=8, offset=0, status="", query=""):
    if not 1 <= limit <= 20 or offset < 0:
        raise ValueError("limit must be 1..20; offset must be nonnegative")
    aliases = {"烟花":"fireworks","粒子":"particles","水":"water","火":"fire","散点":"scatter"}
    word = aliases.get(topic.lower().strip(), topic.lower().strip())
    cards = []
    paths = {p.parent.name:p for p in (example() / "records").glob("*/card.json")}
    paths.update({p.parent.name:p for p in (home() / "records").glob("*/card.json")})
    for path in paths.values():
        card = read(path)
        if kind and card["kind"] != kind:
            continue
        if status and card["status"] != status:
            continue
        if query and query.casefold() not in (card["title"] + " " + card["summary"]).casefold():
            continue
        if word and word not in (s.lower() for s in card["topics"]) and word != card["id"]:
            continue
        cards.append((path.stat().st_mtime_ns, card))
    cards.sort(key=lambda pair: (pair[0],pair[1]["id"]), reverse=True)
    end = offset + limit
    return {"total": len(cards), "next_offset":end if end < len(cards) else None,
            "cards": [c for _, c in cards[offset:end]]}
