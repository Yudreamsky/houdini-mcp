"""Own a serial, idle-expiring hython process for exploratory calls by this MCP server."""
import atexit
import os
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import cancel
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


def wait_process(proc, timeout):
    """proc.wait(timeout) that raises Cancelled as soon as the tool call is cancelled; the caller ends the process."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return proc.wait(timeout=min(.1, max(0., deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(proc.args, timeout) from None
            cancel.check()


@contextmanager
def held(lock):
    """Hold a lock; a cancelled tool call stops waiting for it."""
    while not lock.acquire(timeout=.1):
        cancel.check()
    try:
        yield
    finally:
        lock.release()


class WorkerPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.fresh = None
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
        """At exit. A request that is still rendering holds the lock; its processes end all the same."""
        if self.lock.acquire(timeout=2):
            try:
                self._stop()
            finally:
                self.lock.release()
        else:
            for proc in (self.fresh, self.proc):
                if proc is not None:
                    kill_tree(proc)

    def dispatch(self, install, req, job, fresh=False, timeout=None):
        """timeout: seconds this request may take, for one that renders several frames; the configured limit otherwise."""
        mode = os.environ.get("HOUDINI_RESEARCH_WORKER", "warm").lower()
        if mode not in {"warm","spawn"}:
            raise ValueError("HOUDINI_RESEARCH_WORKER must be warm or spawn")
        timeout = seconds("HOUDINI_RESEARCH_WORKER_TIMEOUT", 600) if timeout is None else timeout
        env = dict(os.environ, HOUDINI_MAXTHREADS=os.environ.get("HOUDINI_MAXTHREADS", "8"))
        options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env)
        job = Path(job).resolve()
        write(job / "request.json", req)
        with held(self.lock):
            if fresh or mode == "spawn" or req["action"] not in WARM_ACTIONS:
                # Release our interactive exploration licence before taking a fresh one.
                self._stop()
                fresh_proc = self.fresh = subprocess.Popen([str(install.hython), str(SCRIPT), str(job)], **options)
                try:
                    wait_process(fresh_proc, timeout)
                except (subprocess.TimeoutExpired, cancel.Cancelled):
                    kill_tree(fresh_proc)
                    raise
                finally:
                    self.fresh = None
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
                        cancel.check()  # a cancelled call ends the worker and the renderers it started, below
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
