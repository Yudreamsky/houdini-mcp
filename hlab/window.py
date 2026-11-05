"""Start or find the dedicated Windows GUI. A launcher lock serializes concurrent clients."""
import msvcrt
import os
import subprocess
import time
from pathlib import Path

from .storage import home, read


def active(directory):
    bridge = directory / "bridge"
    try:
        with (bridge / "active.lock").open("r+b") as handle:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return read(bridge / "session.json")
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except FileNotFoundError:
        pass
    return None


def registered(root, scene_only=False):
    """Yield live, bridge-managed GUI sessions, ignoring stale registrations."""
    directories = list(root.glob("scene-windows/*"))
    if not scene_only:
        directories += [root, *root.glob("shots/*/windows/*")]
    for directory in sorted(directories):
        if directory.is_dir():
            session = active(directory)
            if session:
                yield directory, session


def manage(root, action, session_id="", hip=""):
    from .bridge import call_in
    sessions = list(registered(root))
    if action == "list":
        return {"windows": [s for _, s in sessions]}
    if action not in ("state", "open", "save"):
        raise ValueError("Use list, state, open or save")
    if action == "open":
        from .sop_lab import hip_path
        hip = str(hip_path(hip))
    for directory, session in sessions:
        if session["id"] == session_id:
            if action == "save":
                return call_in(directory, "window_save", expected_session=session_id, hip=hip)
            return call_in(directory, "window_hip", expected_session=session_id,
                           hip=hip if action == "open" else "")
    raise ValueError("The selected session is not live; list windows again")


def ensure(directory=None, executable=None, hip=None):
    directory = Path(directory or home()).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    deadline = time.monotonic()+80
    with (directory/"launch.lock").open("a+b") as guard:
        guard.seek(0)
        while True:
            try:
                msvcrt.locking(guard.fileno(),msvcrt.LK_NBLCK,1)
                break
            except OSError:
                if time.monotonic()>deadline:
                    raise TimeoutError("Another research window is still starting")
                time.sleep(.25)
        existing = active(directory)
        if existing:
            return existing
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ,HOUDINI_RESEARCH_HOME=str(directory),HOUDINI_RESEARCH_ROOT=str(root))
        env["HOUDINI_PATH"] = str(root/"houdini") + os.pathsep + (env.get("HOUDINI_PATH") or "&")
        from .runtime import discover
        install = discover(executable)
        executable = str(install.gui)
        # The visible GUI must not retain the MCP stdio pipes when the client disconnects.
        command = [executable, str(hip)] if hip else [executable]
        process = subprocess.Popen(command,env=env,cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        while time.monotonic()<deadline:
            existing = active(directory)
            if existing and existing["pid"]==process.pid:
                return {**existing, **({"warnings":[install.warning]} if install.warning else {})}
            if process.poll() is not None:
                raise RuntimeError(f"Houdini closed during startup (exit {process.returncode})")
            time.sleep(.2)
        raise TimeoutError(f"Houdini PID {process.pid} has not registered; inspect its visible window")
