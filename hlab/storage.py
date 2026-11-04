import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
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


def example(domain="fireworks"):
    return Path(__file__).resolve().parents[1] / "examples" / domain / "library"


def bundled_libraries():
    return (example(), example("rain"), example("mechanisms"))


def stored(*parts):
    local = home().joinpath(*parts)
    for root in (home(), *bundled_libraries()):
        path=root.joinpath(*parts)
        if path.exists():return path
    return local


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
    with path.open("rb") as data:
        return hashlib.file_digest(data,"sha256").hexdigest()


def created_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def index_published(path):
    from .knowledge_index import published
    published(home(), path)


def record(kind, title, topics, summary, details, parent=None, status="observed"):
    key = uid()
    path = home() / "records" / key
    card = dict(id=key, kind=kind, title=title, topics=topics, summary=summary, status=status, parent=parent, created_at=created_now())
    write(path / "details.json", details)
    write(path / "card.json", card)
    index_published(path / "card.json")
    return card


def details(key):
    card = stored("records", ident(key), "card.json")
    return {**read(card), "details": read(card.with_name("details.json"))}


def search(topic="", kind="", limit=8, offset=0, status="", query=""):
    if not 0 <= limit <= 20 or offset < 0:
        raise ValueError("limit must be 1..20; offset must be nonnegative")
    from .knowledge_index import find
    local = home()
    return find(local, (local, *bundled_libraries()), topic, kind, limit, offset, status, query)
