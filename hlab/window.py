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


def ensure(directory=None, executable=None):
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
        executable = executable or env.get("HOUDINI_EXE", r"C:\Program Files\Side Effects Software\Houdini 20.5.487\bin\houdini.exe")
        # The visible GUI must not retain the MCP stdio pipes when the client disconnects.
        process = subprocess.Popen([executable],env=env,cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        while time.monotonic()<deadline:
            existing = active(directory)
            if existing and existing["pid"]==process.pid:
                return existing
            if process.poll() is not None:
                raise RuntimeError(f"Houdini closed during startup (exit {process.returncode})")
            time.sleep(.2)
        raise TimeoutError(f"Houdini PID {process.pid} has not registered; inspect its visible window")
