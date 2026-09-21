import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from houdini_mcp_local.protocol import HoudiniClient, receive, send
from houdini_mcp_local.service import LocalService


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "session.json"
        self.calls = []

        def dispatch(command, params):
            self.calls.append((command, threading.get_ident()))
            return {"echo": params}

        self.service = LocalService(dispatch, self.path)
        self.service.start()
        self.client = HoudiniClient(self.path)

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def in_thread(self, operation):
        output = []

        def run():
            try:
                output.append(operation())
            except Exception as exc:
                output.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        return thread, output

    def test_unicode_large_message_and_owner_thread(self):
        payload = {"text": "发光地图🌏" * 20000}
        thread, output = self.in_thread(lambda: self.client.call("echo", payload, timeout=3))
        deadline = time.monotonic() + 4
        while thread.is_alive() and time.monotonic() < deadline:
            self.service.drain_one()
            time.sleep(0.005)
        thread.join(1)
        self.assertEqual(output, [{"echo": payload}])
        self.assertEqual(self.calls, [("echo", threading.get_ident())])

    def test_expired_queued_write_is_never_executed(self):
        thread, output = self.in_thread(lambda: self.client.call("write", timeout=0.05))
        thread.join(1)
        self.assertIsInstance(output[0], RuntimeError)
        self.service.drain_one()
        self.assertEqual(self.calls, [])

    def test_wrong_token_cannot_enqueue(self):
        descriptor = json.loads(self.path.read_text())
        with socket.create_connection((descriptor["host"], descriptor["port"])) as sock:
            send(sock, {"request_id": "test", "session_id": descriptor["session_id"], "token": "wrong", "command": "write"})
            response = receive(sock)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "PermissionError")
        self.assertTrue(self.service.jobs.empty())

    def test_worker_thread_cannot_drain(self):
        thread, output = self.in_thread(self.service.drain_one)
        thread.join(1)
        self.assertIsInstance(output[0], RuntimeError)

    def test_live_session_is_not_silently_replaced(self):
        other = LocalService(lambda *args: None, self.path)
        with self.assertRaisesRegex(RuntimeError, "live service"):
            other.start()


if __name__ == "__main__":
    unittest.main()
