"""Exercise actual Houdini undo history in a disposable GUI. Pass the installed houdini.exe path."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hlab.bridge import call_in
from hlab.storage import read, write


STARTUP = """
import os, sys, hou
sys.path.insert(0, os.environ["HOUDINI_RESEARCH_ROOT"])
from hlab import host, scene
from hutil.Qt import QtCore, QtGui

def history():
    return {"undo":hou.undos.undoLabels(), "redo":hou.undos.redoLabels(),
            "active":getattr(hou.session,"hr_active_path",None), "objects":[n.path() for n in hou.node("/obj").children()],
            "frame":hou.frame(),"fps":hou.fps(),"range":tuple(hou.playbar.frameRange())}
def user_drag():
    with hou.undos.group("Artist: drag"):
        scene.parameter("drag").set(2.0)
def shortcut(redo=False):
    # Send the real GUI shortcut only when this dedicated test window owns focus.
    import ctypes
    from ctypes import wintypes
    api=ctypes.windll.user32
    api.GetForegroundWindow.restype=wintypes.HWND
    api.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    window=hou.qt.mainWindow()
    owner=wintypes.DWORD()
    api.GetWindowThreadProcessId(api.GetForegroundWindow(),ctypes.byref(owner))
    if owner.value!=os.getpid():
        return "not_foreground"
    class Keyboard(ctypes.Structure):
        _fields_=[("vk",wintypes.WORD),("scan",wintypes.WORD),("flags",wintypes.DWORD),("time",wintypes.DWORD),("extra",ctypes.c_size_t)]
    class Payload(ctypes.Union):
        _fields_=[("keyboard",Keyboard),("padding",ctypes.c_byte*(32 if ctypes.sizeof(ctypes.c_void_p)==8 else 24))]
    class Input(ctypes.Structure):
        _fields_=[("type",wintypes.DWORD),("payload",Payload)]
    vk=ord("Y" if redo else "Z")
    events=(Input*4)()
    for event,(code,flags) in zip(events,[(0x11,0),(vk,0),(vk,2),(0x11,2)]):
        event.type=1;event.payload.keyboard.vk=code;event.payload.keyboard.flags=flags
    # Houdini routes hotkeys by pane under cursor. Select an interior point of this window.
    before=QtGui.QCursor.pos()
    point=window.mapToGlobal(QtCore.QPoint(window.width()//3,window.height()//2))
    api.WindowFromPoint.argtypes=(wintypes.POINT,)
    api.WindowFromPoint.restype=wintypes.HWND
    under=api.WindowFromPoint(wintypes.POINT(point.x(),point.y()))
    api.GetWindowThreadProcessId(under,ctypes.byref(owner))
    if owner.value!=os.getpid():
        return "point_is_outside_fixture"
    QtGui.QCursor.setPos(point)
    api.GetWindowThreadProcessId(api.GetForegroundWindow(),ctypes.byref(owner))
    queued=owner.value==os.getpid() and api.SendInput(4,events,ctypes.sizeof(Input))==4
    QtCore.QTimer.singleShot(250,lambda: QtGui.QCursor.setPos(before) if QtGui.QCursor.pos()==point else None)
    return "queued" if queued else "not_queued"
def open_test_shot(path):
    hou.hipFile.load(path,suppress_save_prompt=True)
scene.ACTIONS.update(qa_history=history,qa_user_drag=user_drag,qa_shortcut=shortcut,
                     qa_undo=lambda: hou.undos.performUndo(),qa_redo=lambda: hou.undos.performRedo(),qa_open_shot=open_test_shot,
                     qa_hotkeys=lambda:hou.hotkeys.resolveAssignments(("h",),("h.undo","h.redo")))
host.start()
"""


def main(executable):
    repo = Path(__file__).resolve().parents[1]
    (repo/".research").mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(dir=repo/".research",prefix="undo-accept-"))
    plugin = directory/"plugin"
    script = plugin/"python3.11libs"/"uiready.py"
    script.parent.mkdir(parents=True)
    script.write_text(STARTUP,encoding="utf8")
    env = dict(os.environ,HOUDINI_RESEARCH_ROOT=str(repo),HOUDINI_RESEARCH_HOME=str(directory),
               HOUDINI_PATH=str(plugin)+os.pathsep+(os.environ.get("HOUDINI_PATH") or "&"))
    events = {}
    def call(op,**args):
        return call_in(directory,op,**args)
    def history():
        return call("qa_history")
    with (directory/"houdini.log").open("w",encoding="utf8") as log:
        gui=subprocess.Popen([str(executable)],env=env,cwd=repo,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        try:
            print("Disposable undo GUI",gui.pid,directory,flush=True)
            end = time.monotonic()+100
            while not (directory/"bridge/session.json").exists() and time.monotonic()<end:
                time.sleep(.1)
            assert read(directory/"bridge/session.json")["pid"]==gui.pid
            original = history()
            fixture = call("initialize")
            assert history()["undo"][0]=="MCP: initialize", history()
            call("qa_undo")
            cleared=history()
            assert cleared["objects"]==original["objects"] and not cleared["active"], cleared
            assert cleared["frame"]==original["frame"] and cleared["range"]==original["range"],cleared
            call("qa_redo")
            assert call("state")==fixture
            events["initialize_undo_redo"]=True

            call("qa_user_drag")
            before=call("state"); initial_history=history()["undo"]
            change=call("set_controls",changes={"speed":5,"gravity":2})
            assert history()["undo"]==["MCP: set_controls",*initial_history],history()
            bindings=call("qa_hotkeys")
            assert "Ctrl+Z" in bindings[0] and ("Ctrl+Y" in bindings[1] or "Ctrl+Shift+Z" in bindings[1]),bindings
            events["native_key_bindings"]=bindings
            events["shortcut_dispatch"]=call("qa_shortcut")
            time.sleep(.35)
            shortcut_worked=call("state")==before
            if not shortcut_worked:
                call("qa_undo")
            assert call("state")==before and before["parameters"]["drag"]==2.0
            call("qa_redo"); assert call("state")==change
            events["actual_ctrl_z"]=shortcut_worked
            events["adjust_history"]=history()["undo"][:4]
            for op,args in [("set_controls",{"changes":{"speed":500}})]:
                old=history()
                try:
                    call(op,**args)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("invalid operation succeeded")
                assert history()==old and call("state")==change
            old=history()
            experiment=call("sweep",control="npts",samples=[32,96],frame=36)
            assert len(experiment["id"])==32
            assert old==history() and call("state")==change
            events["probe_kept_history"]=True

            chosen=call("checkpoint",title="undo trial",reason="disposable fixture")
            os.environ["HOUDINI_RESEARCH_HOME"]=str(directory)
            from hlab.sop_lab import verify_recipe
            witness=verify_recipe(chosen["id"])
            call("set_controls",changes={"speed":4.8})
            previous=call("state")
            old=history()
            bad={**witness,"geometry_match":False,"reuse_status":"conflict"}
            try:
                call("replay",key=chosen["id"],fresh_check=bad)
            except RuntimeError:
                pass
            else:
                raise AssertionError("conflicting replay succeeded")
            assert call("state")==previous and history()==old,history()
            replay=call("replay",key=chosen["id"],fresh_check=witness)
            assert replay["verified"] and replay["state"]["path"] != previous["path"],replay
            assert history()["undo"]==["MCP: replay",*old["undo"]],history()
            call("qa_undo")
            assert call("state")==previous and replay["state"]["path"] not in history()["objects"]
            call("qa_redo")
            assert call("state")==replay["state"]
            events.update(replay_reuse_id=replay["reuse_id"],fresh_process=witness["process"],version=fixture["version"])
            if len(sys.argv)>2:
                call("qa_open_shot",path=str(Path(sys.argv[2]).resolve(strict=True)))
                smoke=call("afterglow_live")
                old=history()["undo"]
                new_smoke=call("afterglow_live",changes={"smoke":.42,"flash":1.17},frame=53)
                assert history()["undo"]==["MCP: afterglow_live",*old]
                call("qa_undo")
                assert call("afterglow_live")==smoke
                call("qa_redo")
                assert call("afterglow_live")==new_smoke
                events["afterglow_undo_redo"]=True
            write(directory/"acceptance.json", events)
            print(json.dumps(events,ensure_ascii=False),flush=True)
        finally:
            if gui.poll() is None:
                gui.terminate()
            gui.wait(timeout=15)


if __name__=="__main__":
    main(Path(sys.argv[1]).resolve(strict=True))
