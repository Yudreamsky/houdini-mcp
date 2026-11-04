import json
import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hlab import bridge, bridge_queue as queue
from hlab.storage import read, write


def publish_from_process(box, commands, acknowledgements):
    for ticket in iter(commands.get, None):
        # Deliberately identical time in both publishers.
        with patch("hlab.bridge_queue.time.time_ns", return_value=100):
            name = queue.publish(box, {"op":"state", "args":{"ticket":ticket}, "protocol":2,
                                       "deadline":time.time()+60})
        acknowledgements.put(name)


class BridgeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.root = self.directory/"bridge"
        self.box = self.root/"test-session"
        queue.prepare(self.box)
        session = {"id":self.box.name, "protocol":2}
        write(self.root/"session.json", session)
        self.enterContext(patch("hlab.bridge.active", return_value=session))

    def request(self, op="state", **args):
        return {"op":op, "args":args, "protocol":2, "deadline":time.time()+60}

    def events(self):
        return [json.loads(line) for line in (self.root/"orphans.log").read_text().splitlines()]

    def test_budgets_scale_by_capture_count(self):
        self.assertEqual(bridge.operation_timeout("state", {}), 15)
        self.assertEqual(bridge.operation_timeout("capture", {}), 30)
        self.assertEqual(bridge.operation_timeout("graph_capture", {}), 30)
        self.assertEqual(bridge.operation_timeout("live_study", {"action":"motion", "frames":list(range(48))}), 1455)
        self.assertEqual(bridge.operation_timeout("live_study", {"action":"compare", "variants":{"A":{}, "B":{}}, "frames":[3,6,9]}), 195)
        self.assertEqual(bridge.operation_timeout("live_study", {"action":"sweep", "values":[20,40,60,80]}), 135)
        self.assertGreater(bridge.operation_timeout("motion", {"start":1,"end":48}), 120)
        self.assertGreater(bridge.operation_timeout("compare", {"frames":[1,2,3,4]}), 3*4*29)
        self.assertGreater(bridge.operation_timeout("sweep", {"samples":[1,2,3]}), 3*29)
        self.assertGreater(bridge.operation_timeout("window_hip", {"hip":"scene.hip"}), 15)

    def test_expired_while_queued_is_never_dispatched(self):
        with self.assertRaisesRegex(TimeoutError, "before execution"):
            bridge.call_in(self.directory, "state", timeout_seconds=.06)
        self.assertFalse(queue.process_one(self.box, lambda *_: self.fail("Expired request executed")))
        self.assertEqual(self.events()[-1]["outcome"], "not_executed")

    def test_running_timeout_is_not_retried_or_left_in_out(self):
        release = threading.Event()
        observed = []
        claims = []
        def invoke():
            try:
                bridge.call_in(self.directory, "capture", timeout_seconds=.40, frame=36)
            except TimeoutError as exc:
                observed.append(str(exc))
            finally:
                release.set()
        def slow_capture(op, args):
            claims.append((op,args))
            self.assertTrue(release.wait(3))
            return {"image":"late"}
        caller = threading.Thread(target=invoke)
        caller.start()
        try:
            limit = time.monotonic()+3
            while not list((self.box/"in").glob("*.json")) and time.monotonic()<limit:
                time.sleep(.002)
            self.assertTrue(queue.process_one(self.box, slow_capture))
        finally:
            release.set()
            caller.join(timeout=4)
        self.assertEqual(claims, [("capture",{"frame":36})])
        self.assertTrue(observed and "may have executed" in observed[0], observed)
        self.assertFalse(queue.process_one(self.box, slow_capture))
        self.assertEqual(self.events()[-1]["outcome"], "completed_after_timeout")
        for directory in ("in","running","out","cancel"):
            self.assertEqual(list((self.box/directory).glob("*.json")), [])
        name = queue.publish(self.box, self.request())
        self.assertTrue(queue.process_one(self.box, lambda *_: "still available"))
        self.assertEqual(read(self.box/"out"/name), {"ok":"still available"})

    def test_host_and_client_on_opposite_sides_of_timeout_boundary(self):
        request = self.request()
        name = queue.publish(self.box,request)
        with patch("hlab.bridge_queue.time.time",return_value=request["deadline"]+1):
            queue.process_one(self.box,lambda *_:self.fail("expired"))
        self.assertEqual(queue.withdraw(self.box,name,"state"), ("not_executed",None))
        name = queue.publish(self.box,self.request())
        queue.process_one(self.box,lambda *_:"done")
        self.assertEqual(queue.withdraw(self.box,name,"state"),("reply",{"ok":"done"}))

    def test_two_processes_alternate_under_equal_clocks_in_publication_order(self):
        context = multiprocessing.get_context("spawn")
        ack = context.Queue()
        commands = [context.Queue(),context.Queue()]
        publishers = [context.Process(target=publish_from_process,args=(self.box,q,ack)) for q in commands]
        for process in publishers:
            process.start()
        try:
            names = []
            for ticket in range(10):
                commands[ticket % 2].put(ticket)
                names.append(ack.get(timeout=20))
            self.assertEqual(len(set(names)),10)
            self.assertEqual(names,sorted(names))
            received = []
            while queue.process_one(self.box, lambda _,a: received.append(a["ticket"])):
                pass
            self.assertEqual(received, list(range(10)))
        finally:
            for q in commands:
                q.put(None)
            for process in publishers:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join()
                process.close()
            for q in [*commands,ack]:
                q.close()
                q.join_thread()

    def test_reads_legacy_inbox_and_purges_only_old_receipts(self):
        name = "a"*32+".json"
        legacy = self.request()
        del legacy["protocol"]
        write(self.box/"in"/name,legacy)
        queue.process_one(self.box,lambda *_: "old-name")
        fresh = self.box/"out"/name
        self.assertEqual(read(fresh),{"ok":"old-name"})
        stale = self.box/"out"/"stale.json"
        write(stale,{})
        os.utime(stale,(0,0))
        queue.cleanup(self.root)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_new_client_uses_old_host_wire_format_without_restarting_window(self):
        session = {"id": self.box.name}
        write(self.root/"session.json", session)
        requests = []
        def serve():
            limit = time.monotonic()+3
            while time.monotonic()<limit:
                item = next((self.box/"in").glob("*.json"), None)
                if item:
                    requests.append((item.name, read(item)))
                    write(self.box/"out"/item.name, {"ok":"legacy state"})
                    item.unlink()
                    return
                time.sleep(.003)
        worker = threading.Thread(target=serve)
        with patch("hlab.bridge.active", return_value=session):
            worker.start()
            try:
                self.assertEqual(bridge.call_in(self.directory,"state",timeout_seconds=3), "legacy state")
            finally:
                worker.join(4)
        name, request = requests[0]
        self.assertRegex(name, r"^[0-9a-f]{32}\.json$")
        self.assertEqual(set(request), {"op", "args", "deadline"})
        self.assertFalse((self.box/"queue.lock").exists())

    def test_reply_publication_failure_never_reexecutes_action(self):
        name = queue.publish(self.box,self.request())
        seen = []
        with patch("hlab.bridge_queue.write",side_effect=OSError("write failed")), self.assertRaises(OSError):
            queue.process_one(self.box, lambda op,_: seen.append(op))
        self.assertFalse(queue.process_one(self.box,lambda op,_:seen.append(op)))
        self.assertEqual(seen,["state"])
        self.assertTrue((self.box/"running"/name).exists())
