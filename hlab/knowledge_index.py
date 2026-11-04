"""A disposable FTS index of JSON summaries. Local cards take precedence over bundled copies."""
import json
import os
import sqlite3
import sysconfig
import time
import unicodedata
from contextlib import closing
from datetime import datetime
from pathlib import Path


SCHEMA = 2
INDEX_NAME = "knowledge.sqlite3"


def normalize(value):
    return unicodedata.normalize("NFKC", value).casefold().strip()


def vocabulary():
    path = Path(__file__).resolve().parents[1] / "skills/houdini-research/references/topics.json"
    if not path.is_file():
        path = Path(sysconfig.get_path("data")) / "share/houdini-research/topics.json"
    groups = json.loads(path.read_text(encoding="utf8"))
    lookup = {}
    for canonical, aliases in groups.items():
        terms = tuple(dict.fromkeys(normalize(term) for term in (canonical, *aliases)))
        for term in terms:
            lookup[term] = terms
    return lookup


def ensure_schema(db):
    if db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA:
        return
    for table in ("card_fts", "tags", "cards"):
        db.execute(f"DROP TABLE IF EXISTS {table}")
    db.execute("""CREATE TABLE cards (
        id TEXT PRIMARY KEY, source TEXT NOT NULL, modified_ns INTEGER NOT NULL, size INTEGER NOT NULL,
        kind TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
        title TEXT NOT NULL, summary TEXT NOT NULL, payload TEXT NOT NULL)""")
    db.execute("CREATE INDEX cards_by_time ON cards(created_at DESC,id DESC)")
    db.execute("CREATE TABLE tags (tag TEXT, id TEXT, PRIMARY KEY (tag,id)) WITHOUT ROWID")
    db.execute("CREATE INDEX tags_by_card ON tags(id)")
    db.execute("CREATE VIRTUAL TABLE card_fts USING fts5(body, tokenize='trigram')")
    db.execute(f"PRAGMA user_version={SCHEMA}")


def transact(folder, operation):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / INDEX_NAME
    for attempt in range(2):
        try:
            with closing(sqlite3.connect(path, timeout=20)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                ensure_schema(db)
                return operation(db)
        except sqlite3.DatabaseError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 255
            if attempt or code not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                raise
            recover(path)


def recover(path):
    # Use a separate SQLite file lock only for recovery: a corrupt database cannot
    # arbitrate its own replacement. Other clients may already have repaired it.
    with closing(sqlite3.connect(path.with_suffix(".recovery"), timeout=20)) as gate:
        gate.execute("BEGIN IMMEDIATE")
        with closing(sqlite3.connect(path, timeout=20)) as probe:
            try:
                if probe.execute("PRAGMA quick_check").fetchone()[0] == "ok":
                    return
            except sqlite3.DatabaseError as exc:
                if (getattr(exc, "sqlite_errorcode", 0) & 255) not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                    raise
        for attempt in range(30):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                # Windows will release the file after competing readers close their failed connections.
                if attempt == 29:
                    raise
                time.sleep(.02)


def remove(db, key):
    db.execute("DELETE FROM card_fts WHERE rowid=(SELECT rowid FROM cards WHERE id=?)", (key,))
    db.execute("DELETE FROM tags WHERE id=?", (key,))
    db.execute("DELETE FROM cards WHERE id=?", (key,))


def index_card(db, key, path, modified, size):
    raw = Path(path).read_text(encoding="utf8")
    card = json.loads(raw)
    if key != card["id"]:
        raise ValueError(f"Card ID does not match its directory: {path}")
    title, summary = normalize(card["title"]), normalize(card["summary"])
    created = datetime.fromisoformat(card["created_at"]).timestamp() if card.get("created_at") else modified / 1e9
    remove(db, key)
    row = db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (key,path,modified,size,card["kind"],card["status"],created,title,summary,raw)).lastrowid
    db.execute("INSERT INTO card_fts(rowid,body) VALUES (?,?)", (row,title+" "+summary))
    db.executemany("INSERT OR IGNORE INTO tags(tag,id) VALUES (?,?)",
                   [(normalize(tag),key) for tag in card["topics"]])


def published(folder, path):
    def update(db):
        stat = path.stat()
        index_card(db, path.parent.name, str(path), stat.st_mtime_ns, stat.st_size)
    try:
        transact(folder, update)
    except sqlite3.OperationalError:
        # The JSON write has already succeeded (e.g. another process holds this cache).
        # Reconciliation on search will pick it up even if this writer exits now.
        pass


def snapshot(roots):
    paths = {}
    for root in roots:
        try:
            folders = os.scandir(root / "records")
        except FileNotFoundError:
            continue
        with folders:
            for entry in folders:
                if entry.name in paths or not entry.is_dir():
                    continue
                path = os.path.join(entry.path, "card.json")
                try:
                    stat = os.stat(path)
                except FileNotFoundError:
                    continue
                paths[entry.name] = (path, stat.st_mtime_ns, stat.st_size)
    return paths


def reconcile(db, roots):
    known = {key:(source,mtime,size) for key,source,mtime,size in
             db.execute("SELECT id,source,modified_ns,size FROM cards")}
    paths = snapshot(roots)
    for key in known.keys() - paths.keys():
        remove(db, key)
    for key, signature in paths.items():
        if signature != known.get(key):
            try:
                index_card(db, key, *signature)
            except FileNotFoundError:
                # A folder can disappear between stat and read, including on a branch switch.
                remove(db, key)


def find(folder, roots, topic, kind, limit, offset, status, query):
    aliases = vocabulary()
    clauses = []
    values = []
    for column,value in (("kind",kind), ("status",status)):
        if value:
            clauses.append(f"{column}=?")
            values.append(value)
    topic = normalize(topic)
    if topic:
        terms = aliases.get(topic, (topic,))
        slots = ",".join("?" for _ in terms)
        clauses.append(f"(id=? OR id IN (SELECT id FROM tags WHERE tag IN ({slots})))")
        values.extend([topic, *terms])
    query = normalize(query)
    # Preserve literal substring matching (including punctuation). Single and double
    # characters cannot use a trigram index, so only these terms use instr().
    if query:
        terms = aliases.get(query, (query,))
        group = []
        long_terms = [term for term in terms if len(term) >= 3]
        if long_terms:
            group.append("rowid IN (SELECT rowid FROM card_fts WHERE card_fts MATCH ?)")
            values.append(" OR ".join('"'+t.replace('"','""')+'"' for t in long_terms))
        for short in (t for t in terms if len(t)<3):
            group.append("instr(title||' '||summary,?)>0")
            values.append(short)
        clauses.append("("+" OR ".join(group)+")")
    where = " WHERE "+" AND ".join(clauses) if clauses else ""
    def lookup(db):
        reconcile(db, roots)
        total = db.execute("SELECT count(*) FROM cards"+where, values).fetchone()[0]
        rows = db.execute("SELECT payload FROM cards"+where+" ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                          [*values,limit,offset])
        return {"total":total, "next_offset":offset+limit if offset+limit<total else None,
                "cards":[json.loads(row[0]) for row in rows]}
    return transact(folder, lookup)
