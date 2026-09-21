"""Local transport queues work; only the owner thread touches Houdini."""

import hmac
import json
import os
import queue
import secrets
import socket
import socketserver
import threading
import time
import uuid
from pathlib import Path

from .protocol import PROTOCOL_VERSION, receive, send


class Job:
    def __init__(self, request):
        self.request = request
        timeout = float(request.get("timeout", 120))
        if not 0 < timeout <= 120:
            raise ValueError("timeout must be in (0, 120]")
        self.deadline = time.monotonic() + timeout
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.state = "queued"
        self.response = None


def failure(request, kind, message):
    return {"request_id": request.get("request_id"), "ok": False,
            "error": {"type": kind, "message": message}}


class LocalService:
    def __init__(self, dispatch, session_file, metadata=None):
        self.dispatch = dispatch
        self.session_file = Path(session_file).resolve()
        self.owner_thread = threading.get_ident()
        self.jobs = queue.Queue(maxsize=32)
        self.running = False
        self.token = secrets.token_urlsafe(32)
        self.session_id = str(uuid.uuid4())
        self.metadata = metadata or {}
        self.server = None

    def start(self):
        if self.running:
            return
        if self.session_file.exists():
            old = json.loads(self.session_file.read_text(encoding="utf-8"))
            if old.get("host") == "127.0.0.1":
                try:
                    with socket.create_connection((old["host"], old["port"]), timeout=0.3):
                        pass
                except OSError:
                    pass
                else:
                    raise RuntimeError("This session file belongs to a live service; choose another file")
        service = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                request = {}
                try:
                    self.request.settimeout(5)
                    request = receive(self.request)
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object")
                    valid = hmac.compare_digest(str(request.get("token", "")), service.token)
                    if not valid or request.get("session_id") != service.session_id:
                        send(self.request, failure(request, "PermissionError", "Invalid session credentials"))
                        return
                    if not service.running:
                        raise RuntimeError("Service is stopping")
                    job = Job(request)
                    service.jobs.put_nowait(job)
                    if not job.event.wait(max(0, job.deadline - time.monotonic())):
                        with job.lock:
                            if job.state == "queued":
                                job.state = "cancelled"
                                response = failure(request, "TimeoutError", "Expired before execution; cancelled")
                            elif job.state == "done":
                                response = job.response
                            else:
                                response = failure(request, "TimeoutError", "Execution already started; outcome unknown. Do not blindly retry.")
                    else:
                        response = job.response
                    send(self.request, response)
                except Exception as exc:
                    try:
                        send(self.request, failure(request if isinstance(request, dict) else {}, type(exc).__name__, str(exc)))
                    except OSError:
                        pass

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        self.server = Server(("127.0.0.1", 0), Handler)
        self.running = True
        descriptor = {
            "protocol": PROTOCOL_VERSION, "host": "127.0.0.1",
            "port": self.server.server_address[1], "pid": os.getpid(),
            "session_id": self.session_id, "token": self.token, **self.metadata,
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.session_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
        temporary.replace(self.session_file)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()

    def drain_one(self):
        if threading.get_ident() != self.owner_thread:
            raise RuntimeError("Houdini commands must execute on the owner thread")
        try:
            job = self.jobs.get_nowait()
        except queue.Empty:
            return
        with job.lock:
            if job.state == "cancelled" or time.monotonic() >= job.deadline:
                job.state = "done"
                job.response = failure(job.request, "TimeoutError", "Expired before execution; cancelled")
                job.event.set()
                return
            job.state = "running"
        try:
            result = self.dispatch(job.request["command"], job.request.get("params", {}))
            response = {"request_id": job.request["request_id"], "ok": True, "result": result}
            json.dumps(response, allow_nan=False)  # fail here instead of returning an unserializable success
        except BaseException as exc:
            response = failure(job.request, type(exc).__name__, str(exc))
        with job.lock:
            job.response = response
            job.state = "done"
            job.event.set()

    def stop(self):
        self.running = False
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            with job.lock:
                job.response = failure(job.request, "ConnectionError", "Service stopped before execution")
                job.state = "done"
                job.event.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.session_file.exists():
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
            if data.get("session_id") == self.session_id:
                self.session_file.unlink()
