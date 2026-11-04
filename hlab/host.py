"""Event-loop side of a local, single-user bridge. Imported inside Houdini only."""
import msvcrt
import os

import hou

from . import bridge_queue, scene
from .storage import home, uid, write

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
    bridge_queue.cleanup(root)
    bridge_queue.prepare(box)
    write(root / "session.json", {"id": key, "pid": os.getpid(), "version": hou.applicationVersionString(), "protocol": 2})
    busy = False

    def dispatch(op, args):
        if hasattr(scene, "dispatch"):
            return scene.dispatch(op, args)
        if op not in scene.ACTIONS:
            raise ValueError("Unknown action")
        return scene.ACTIONS[op](**args)

    def step():
        nonlocal busy
        if busy:
            return
        busy = True
        try:
            bridge_queue.process_one(box, dispatch)
        finally:
            busy = False

    hou.ui.addEventLoopCallback(step)
    if hou.node("/obj/RESIDUAL_SMOKE/First_burst_cache"):
        pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if pane:
            pane.curViewport().setCamera(hou.node("/obj/CAM"))
        hou.node("/obj/DIRECTION").setCurrent(True, clear_all_selected=True)
    if hou.node("/obj/RAIN/ART_DIRECTION"):
        pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if pane:
            pane.curViewport().setCamera(hou.node("/obj/CAM"))
            pane.constructionPlane().setIsVisible(False)
        hou.node("/obj/RAIN/ART_DIRECTION").setCurrent(True,clear_all_selected=True)
