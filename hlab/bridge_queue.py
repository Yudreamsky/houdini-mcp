"""File handoff shared by MCP clients and Houdini's single-threaded GUI dispatcher."""
import errno
import json
import msvcrt
import time
from contextlib import contextmanager

from .storage import read, uid, write


@contextmanager
def locked(box, wait=True):
    # The OS releases this byte-range lock if a publisher or GUI process exits.
    with (box / "queue.lock").open("a+b") as file:
        limit = time.monotonic() + 5
        while True:
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if not wait:
                    yield False
                    return
                if time.monotonic() >= limit:
                    raise TimeoutError("Houdini bridge queue lock is busy") from exc
                time.sleep(.005)
        try:
            yield True
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def prepare(box):
    for name in ("in", "running", "out", "cancel"):
        (box / name).mkdir(parents=True, exist_ok=True)


def publish(box, request):
    # Allocate the sequence and make the request visible in the same critical section.
    with locked(box):
        counter = box / "sequence.json"
        last = read(counter) if counter.exists() else 0
        stamp = max(time.time_ns(), last + 1)
        write(counter, stamp)
        name = f"{stamp:020d}-{uid()}.json"
        write(box / "in" / name, request)
    return name


def order(item):
    prefix, sep, _ = item.name.partition("-")
    # Old clients publish plain UUIDs; preserve their original reply names.
    stamp = int(prefix) if sep and prefix.isdigit() else item.stat().st_mtime_ns
    return stamp, item.name


def note_orphan(box, name, op, outcome):
    event = dict(time=time.time(), session=box.name, request=name, op=op, outcome=outcome)
    with (box.parent / "orphans.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(event) + "\n")


def withdraw(box, name, op):
    """Called only by the owner. A queue claim and a withdrawal cannot both win."""
    with locked(box):
        reply = box / "out" / name
        pending = box / "in" / name
        cancel = box / "cancel" / name
        if reply.exists():
            result = read(reply)
            reply.unlink()
            return "reply", result
        if pending.exists():
            pending.unlink()
            note_orphan(box, name, op, "not_executed")
            return "not_executed", None
        if (box / "running" / name).exists():
            write(cancel, "abandoned")
            return "possibly_executed", None
        if cancel.exists():
            outcome = read(cancel)
            cancel.unlink()
            return outcome, None
        return "possibly_executed", None


def process_one(box, dispatch):
    inbox = box / "in"
    if next(inbox.glob("*.json"), None) is None:
        return False
    with locked(box, wait=False) as acquired:
        if not acquired:
            return False
        item = min(inbox.glob("*.json"), key=order, default=None)
        if item is None:
            return False
        # Claim before doing ANY scene work. Failed reply writes and restarts cannot replay edits.
        running = box / "running" / item.name
        item.rename(running)
    request = {}
    ran = False
    try:
        request = read(running)
        if time.time() >= request["deadline"]:
            raise TimeoutError("Request expired before execution")
        ran = True
        result = {"ok": dispatch(request["op"], request["args"])}
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    with locked(box):
        cancel = box / "cancel" / item.name
        if cancel.exists() or time.time() >= request.get("deadline", float("inf")):
            outcome = ("failed_after_timeout" if "error" in result else "completed_after_timeout") if ran else "not_executed"
            note_orphan(box, item.name, request.get("op"), outcome)
            if cancel.exists():
                cancel.unlink()
            elif request.get("protocol") == 2:
                # Host finished just before the client acquired the queue lock to time out.
                write(cancel, outcome)
        else:
            write(box / "out" / item.name, result)
        running.unlink()
    return True


def cleanup(root, max_age=3600):
    cutoff = time.time() - max_age
    for folder in root.iterdir():
        if folder.is_dir():
            for name in ("out", "cancel", "running"):
                for item in (folder / name).glob("*.json"):
                    try:
                        if item.stat().st_mtime < cutoff:
                            item.unlink()
                    except FileNotFoundError:
                        pass
