"""Length-prefixed JSON transport; no Houdini or MCP imports."""

import json
import socket
import struct
import uuid
from pathlib import Path

MAX_PACKET = 16 * 1024 * 1024
PROTOCOL_VERSION = 1


def receive(sock):
    def exact(count):
        chunks = bytearray()
        while len(chunks) < count:
            part = sock.recv(count - len(chunks))
            if not part:
                raise ConnectionError("Peer disconnected before a complete response")
            chunks.extend(part)
        return bytes(chunks)

    length = struct.unpack("!I", exact(4))[0]
    if length > MAX_PACKET:
        raise ValueError("Packet exceeds size limit")
    return json.loads(exact(length).decode("utf-8"))


def send(sock, value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(payload) > MAX_PACKET:
        raise ValueError("Packet exceeds size limit")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


class HoudiniClient:
    def __init__(self, session_file):
        self.session_file = Path(session_file)

    def call(self, command, params=None, timeout=120):
        if not self.session_file.exists():
            raise ConnectionError("No Houdini session. Run launch_gui.py or start the bridge in Houdini.")
        info = json.loads(self.session_file.read_text(encoding="utf-8"))
        if info.get("host") != "127.0.0.1" or info.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Unsupported session descriptor; only local protocol v1 is supported")
        request_id = str(uuid.uuid4())
        request = {
            "request_id": request_id, "session_id": info["session_id"],
            "token": info["token"], "command": command, "params": params or {},
            "timeout": timeout,
        }
        try:
            with socket.create_connection((info["host"], info["port"]), timeout=3) as sock:
                sock.settimeout(timeout + 5)
                send(sock, request)
                response = receive(sock)
        except (TimeoutError, ConnectionError, OSError) as exc:
            raise ConnectionError(
                f"Houdini transport failed for {request_id}: {exc}. "
                "The outcome may be unknown; inspect the scene before retrying a write."
            ) from exc
        if response.get("request_id") != request_id:
            raise RuntimeError("Response request ID mismatch")
        if not response.get("ok"):
            error = response.get("error", {})
            raise RuntimeError(f"{error.get('type', 'Error')}: {error.get('message', error)}")
        return response["result"]
