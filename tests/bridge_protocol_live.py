"""Real GUI validation of the Windows file bridge. Run with -m tests.bridge_protocol_live <houdini.exe>.

Starts and closes its own Houdini process, using a fresh test data directory.
"""
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from hlab import bridge, bridge_queue
from hlab.storage import read, write


STARTUP = """
import os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["HOUDINI_RESEARCH_ROOT"])
from hlab import host, scene
from hlab.storage import home, read
import hou

home_dir = home()
original_capture = scene.ACTIONS["capture"]
original_state = scene.ACTIONS["state"]
def slow_capture(**args):
    marker = home_dir / "slow-once"
    if marker.is_file():
        marker.unlink()
        time.sleep(1.65)
    return original_capture(**args)
def traced_state():
    root = home_dir/"bridge"
    box = root/read(root/"session.json")["id"]
    current = next((box/"running").glob("*.json"))
    with (home_dir/"state-order.log").open("a", encoding="utf8") as log:
        log.write(current.name + "\\n")
    return original_state()
scene.ACTIONS.update(capture=slow_capture, state=traced_state)
host.start()
if hou.qt.mainWindow():
    hou.qt.mainWindow().setWindowTitle("Houdini Research - disposable bridge protocol acceptance")
"""


def publisher(box, inbox, events):
    for _ in iter(inbox.get, None):
        name = bridge_queue.publish(box, {"op":"state","args":{},"protocol":2,"deadline":time.time()+45})
        events.put(name)


def wait_for(predicate, timeout=20):
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():
            return
        time.sleep(.05)
    raise TimeoutError("Timed out waiting for the disposable bridge fixture")


def live(executable):
    repo = Path(__file__).resolve().parents[1]
    (repo/".research").mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=repo/".research", prefix="bridge-protocol-"))
    env_root = root/"plugin"
    startup = env_root/"python3.11libs"/"uiready.py"
    startup.parent.mkdir(parents=True)
    startup.write_text(STARTUP,encoding="utf8")
    env = dict(os.environ, HOUDINI_RESEARCH_ROOT=str(repo), HOUDINI_RESEARCH_HOME=str(root),
               HOUDINI_PATH=str(env_root)+os.pathsep+(os.environ.get("HOUDINI_PATH") or "&"))
    report = {"home":str(root)}
    with (root/"houdini.log").open("w",encoding="utf8") as log:
        gui = subprocess.Popen([str(executable)],env=env,cwd=repo,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        try:
            print("Disposable GUI",gui.pid,root,flush=True)
            wait_for(lambda:(root/"bridge/session.json").is_file(),100)
            session = read(root/"bridge/session.json")
            assert session["pid"] == gui.pid and session["protocol"] == 2
            box = root/"bridge"/session["id"]
            report.update(pid=gui.pid,version=session["version"])
            bridge.call_in(root,"initialize")
            t = time.monotonic()
            motion = bridge.call_in(root,"motion",start=1,end=48)
            samples = motion["samples"]
            assert [s["frame"] for s in samples] == list(range(1,49))
            assert all((root/"images"/(s["image_id"]+".png")).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for s in samples)
            report.update(motion_frames=len(samples),motion_seconds=round(time.monotonic()-t,2),
                          motion_deadline_seconds=bridge.operation_timeout("motion",{"start":1,"end":48}))
            print("48 actual flipbook frames",report["motion_seconds"],flush=True)

            (root/"slow-once").touch()
            try:
                bridge.call_in(root,"capture",frame=36,timeout_seconds=1)
            except TimeoutError as exc:
                assert "may have executed" in str(exc), exc
                report["timeout_message"] = str(exc)
            else:
                raise AssertionError("Expected an in-flight capture timeout")
            wait_for(lambda:(root/"bridge/orphans.log").is_file() and not any((box/"running").glob("*.json")))
            events = [json.loads(line) for line in (root/"bridge/orphans.log").read_text().splitlines()]
            assert events[-1]["op"]=="capture" and events[-1]["outcome"]=="completed_after_timeout",events
            assert not any((box/"out").glob("*.json")) and not any((box/"cancel").glob("*.json"))
            report["orphan_event"] = events[-1]
            assert bridge.call_in(root,"state")["pid"] == gui.pid

            context = multiprocessing.get_context("spawn")
            out = context.Queue()
            queues = [context.Queue(),context.Queue()]
            children = [context.Process(target=publisher,args=(box,q,out)) for q in queues]
            for child in children:
                child.start()
            try:
                names = []
                for ticket in range(10):
                    queues[ticket%2].put(ticket)
                    names.append(out.get(timeout=20))
                wait_for(lambda:all((box/"out"/name).exists() for name in names))
                actual = (root/"state-order.log").read_text().splitlines()[-10:]
                assert names == actual == sorted(names),(names,actual)
                for name in names:
                    receipt = box/"out"/name
                    assert read(receipt)["ok"]["pid"] == gui.pid
                    receipt.unlink()
                report.update(publishers=2,ordered_requests=len(names),remaining_replies=len(list((box/"out").glob("*.json"))))
            finally:
                for q in queues:
                    q.put(None)
                for child in children:
                    child.join(5)
                    if child.is_alive():
                        child.terminate()
                        child.join()
                    child.close()
                for q in [*queues,out]:
                    q.close()
                    q.join_thread()
            write(root/"acceptance.json", report)
            print(json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            if gui.poll() is None:
                gui.terminate()
            gui.wait(timeout=15)


if __name__=="__main__":
    live(Path(sys.argv[1]).resolve(strict=True))
