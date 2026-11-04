"""Event-loop side of a local, single-user bridge. Imported inside Houdini only."""
import msvcrt
import os
import time

import hou

from . import scene
from .storage import home, read, uid, write

_session_lock = None


def start():
    global _session_lock
    root = home() / "bridge"
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "active.lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return
    _session_lock = lock
    key = uid()
    box = root / key
    inbox = box / "in"
    inbox.mkdir(parents=True)
    (box / "out").mkdir()
    write(root / "session.json", {"id": key, "pid": os.getpid(), "version": hou.applicationVersionString()})
    busy = False

    def step():
        nonlocal busy
        if busy:
            return
        item = next(inbox.glob("*.json"), None)
        if not item:
            return
        busy = True
        try:
            request = read(item)
            if time.time() >= request["deadline"]:
                raise RuntimeError("Request expired before execution")
            if request["op"] not in scene.ACTIONS:
                raise ValueError("Unknown action")
            result = {"ok": scene.ACTIONS[request["op"]](**request["args"])}
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                write(box / "out" / item.name, result)
                item.unlink()
            finally:
                busy = False

    hou.ui.addEventLoopCallback(step)
