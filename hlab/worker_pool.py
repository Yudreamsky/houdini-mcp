"""Own a serial, idle-expiring hython process for exploratory calls by this MCP server."""
import atexit
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .storage import read, write

SCRIPT = Path(__file__).with_name("sop_worker.py")
WARM_ACTIONS = {"nodes", "inspect", "animation_gap", "sweep", "study", "afterglow_render", "karma_inspect", "karma_render"}


def seconds(name, default):
    limit = float(os.environ.get(name, default))
    if not 0 < limit < float("inf"):
        raise ValueError(f"{name} must be a finite positive number of seconds")
    return limit


def kill_tree(proc):
    """End hython and the renderers it started; Windows does not end child processes with their parent."""
    if proc.poll() is None and os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.poll() is None:
        proc.kill()
    proc.wait()


class WorkerPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.mail = None
        self.hython = None
        self.last = 0.0

    def _stop(self):
        if self.proc is not None:
            kill_tree(self.proc)
            self.proc = None
        if self.mail is not None:
            self.mail.cleanup()
            self.mail = None

    def close(self):
        with self.lock:
            self._stop()

    def dispatch(self, install, req, job, fresh=False):
        mode = os.environ.get("HOUDINI_RESEARCH_WORKER", "warm").lower()
        if mode not in {"warm","spawn"}:
            raise ValueError("HOUDINI_RESEARCH_WORKER must be warm or spawn")
        timeout = seconds("HOUDINI_RESEARCH_WORKER_TIMEOUT", 600)
        env = dict(os.environ, HOUDINI_MAXTHREADS=os.environ.get("HOUDINI_MAXTHREADS", "8"))
        options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env)
        job = Path(job).resolve()
        write(job / "request.json", req)
        with self.lock:
            if fresh or mode == "spawn" or req["action"] not in WARM_ACTIONS:
                # Release our interactive exploration licence before taking a fresh one.
                self._stop()
                fresh_proc = subprocess.Popen([str(install.hython), str(SCRIPT), str(job)], **options)
                try:
                    fresh_proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    kill_tree(fresh_proc)
                    raise
                if fresh_proc.returncode:
                    raise subprocess.CalledProcessError(fresh_proc.returncode, fresh_proc.args)
            else:
                idle = seconds("HOUDINI_RESEARCH_WORKER_IDLE", 300)
                if (self.proc is None or self.proc.poll() is not None or self.hython != install.hython
                        or time.monotonic() - self.last >= idle):
                    self._stop()
                    self.mail = tempfile.TemporaryDirectory(prefix="houdini-worker-mail-")
                    self.hython = install.hython
                    self.proc = subprocess.Popen([str(self.hython), str(SCRIPT), "--serve",
                                                  self.mail.name, str(idle)], **options)
                self.last = time.monotonic()
                deadline = self.last + timeout
                write(Path(self.mail.name) / "request.json", {"folder":str(job),"deadline":time.time()+timeout})
                try:
                    while not (job / "reply.json").exists():
                        if self.proc.poll() is not None:
                            raise RuntimeError("Houdini worker exited before replying; request was not retried")
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Houdini worker deadline exceeded; request was not retried")
                        time.sleep(.025)
                except BaseException:
                    self._stop()
                    raise
                self.last = time.monotonic()
        reply = read(job / "reply.json")
        if "ok" in reply and install.warning:
            reply["ok"].setdefault("warnings", []).append(install.warning)
        return reply


pool = WorkerPool()
atexit.register(pool.close)
