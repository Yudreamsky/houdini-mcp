"""Tool bodies run in worker threads: other calls are answered meanwhile, and a cancelled call ends what it started."""
import asyncio
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hlab import bridge, bridge_queue, cancel, karma, vantage, worker_pool
from hlab.storage import write

# Stands in for hython: starts a "renderer" of its own, says so, and waits.
WORKER = """import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
marker = pathlib.Path(os.environ["HR_TEST_MARKER"])
marker.with_suffix(".tmp").write_text(str(child.pid))
marker.with_suffix(".tmp").replace(marker)
time.sleep(120)
"""
SELF = "import os, pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(120)"


def appears(path, seconds=30):
    deadline = time.monotonic() + seconds
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(.05)
    return path.exists()


def running(pid):
    for _ in range(50):
        # The "no tasks" notice is localised, so decode leniently.
        listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True).stdout.decode(errors="replace")
        if pid not in listed.split():
            return False
        time.sleep(.1)
    return True


def in_thread(flag, call, *args, **kwargs):
    """Run call under a cancel flag in its own thread, as a tool body runs; returns the thread and what it raised."""
    raised = []

    def body():
        try:
            cancel.run(flag, call, *args, **kwargs)
        except BaseException as exc:
            raised.append(exc)

    thread = threading.Thread(target=body)
    thread.start()
    return thread, raised


class FlagTests(unittest.TestCase):
    def test_nothing_is_cancelled_outside_a_tool_call(self):
        self.assertFalse(cancel.requested())
        cancel.check()
        cancel.wait(0)

    def test_a_raised_flag_ends_checks_and_pauses(self):
        flag = cancel.new_flag()
        thread, raised = in_thread(flag, cancel.wait, 30)
        started = time.monotonic()
        flag.set()
        thread.join(5)
        self.assertIsInstance(raised[0], cancel.Cancelled)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(isinstance(raised[0], Exception))  # retry code that catches errors must let it pass


class ThreadedToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_other_calls_are_answered_while_one_waits_and_cancelling_reaches_its_loop(self):
        from hlab import server
        started, stopped = threading.Event(), threading.Event()

        def slow():
            started.set()
            try:
                while True:
                    cancel.wait(.02)
            except cancel.Cancelled:
                stopped.set()
                raise

        with (tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": home}),
              patch("hlab.karma.presets", slow)):
            render = asyncio.create_task(server.mcp.call_tool("karma", {"action": "presets"}))
            self.assertTrue(await asyncio.to_thread(started.wait, 10))
            await asyncio.wait_for(server.mcp.call_tool("knowledge", {"topic": "water"}), 10)
            self.assertFalse(render.done())  # still waiting, and the server answered another call
            render.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await render
            self.assertTrue(await asyncio.to_thread(stopped.wait, 10))

    def test_tools_still_call_each_other_as_plain_functions(self):
        from hlab import server
        self.assertFalse(inspect.iscoroutinefunction(server.knowledge))
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": home}):
            self.assertIn("cards", server.knowledge(topic="water"))


@unittest.skipUnless(os.name == "nt", "the worker pool and its process trees are Windows-only")
class ProcessCancelTests(unittest.TestCase):
    def cancelled_dispatch(self, action):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            script, marker, job = folder / "worker.py", folder / "child.pid", folder / "job"
            script.write_text(WORKER)
            job.mkdir()
            pool = worker_pool.WorkerPool()
            install = SimpleNamespace(hython=Path(sys.executable), warning="")
            flag = cancel.new_flag()
            with (patch("hlab.worker_pool.SCRIPT", script),
                  patch.dict(os.environ, {"HR_TEST_MARKER": str(marker), "HOUDINI_RESEARCH_WORKER": "warm"})):
                thread, raised = in_thread(flag, pool.dispatch, install, {"action": action, "hip": "scene.hip"}, job)
                self.assertTrue(appears(marker))
                renderer = marker.read_text()
                started = time.monotonic()
                flag.set()
                thread.join(15)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(raised[0], cancel.Cancelled)
            self.assertLess(time.monotonic() - started, 10)
            self.assertFalse(running(renderer))  # the child the worker started went with it
            self.assertIsNone(pool.proc)
            self.assertTrue(pool.lock.acquire(timeout=1))  # the next request can start
            pool.lock.release()

    def test_a_cancelled_warm_request_ends_the_worker_and_its_renderer(self):
        self.cancelled_dispatch("karma_render")

    def test_a_cancelled_fresh_request_ends_the_worker_and_its_renderer(self):
        self.cancelled_dispatch("mechanism")

    def test_a_request_waiting_for_the_worker_gives_up_when_cancelled(self):
        pool = worker_pool.WorkerPool()
        pool.lock.acquire()  # another request is rendering
        try:
            with tempfile.TemporaryDirectory() as tmp:
                flag = cancel.new_flag()
                install = SimpleNamespace(hython=Path(sys.executable), warning="")
                thread, raised = in_thread(flag, pool.dispatch, install, {"action": "karma_render"}, Path(tmp))
                time.sleep(.3)
                self.assertTrue(thread.is_alive())
                flag.set()
                thread.join(5)
                self.assertIsInstance(raised[0], cancel.Cancelled)
        finally:
            pool.lock.release()

    def test_a_cancelled_render_ends_vantage(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "vantage.pid"
            flag = cancel.new_flag()
            with patch("hlab.vantage.executable", return_value=Path(sys.executable)):
                thread, raised = in_thread(flag, vantage.launch, ["-c", SELF, str(marker)], 300)
                self.assertTrue(appears(marker))
                flag.set()
                thread.join(15)
            self.assertIsInstance(raised[0], cancel.Cancelled)
            self.assertFalse(running(marker.read_text()))


class BridgeCancelTests(unittest.TestCase):
    def test_a_cancelled_live_call_withdraws_a_request_houdini_has_not_started(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        root = directory / "bridge"
        box = root / "test-session"
        bridge_queue.prepare(box)
        session = {"id": box.name, "protocol": 2}
        write(root / "session.json", session)
        flag = cancel.new_flag()
        with patch("hlab.bridge.active", return_value=session):
            thread, raised = in_thread(flag, bridge.call_in, directory, "graph_read", timeout_seconds=60, path="/obj")
            deadline = time.monotonic() + 10
            while not list((box / "in").glob("*.json")) and time.monotonic() < deadline:
                time.sleep(.02)
            flag.set()
            thread.join(5)
        self.assertIsInstance(raised[0], cancel.Cancelled)
        self.assertIn("not_executed", str(raised[0]))
        self.assertEqual(list((box / "in").glob("*.json")), [])
        events = [json.loads(line) for line in (root / "orphans.log").read_text().splitlines()]
        self.assertEqual(events[-1]["outcome"], "not_executed")
        self.assertFalse(bridge_queue.process_one(box, lambda *_: self.fail("a cancelled request reached Houdini")))


class AnimationCancelTests(unittest.TestCase):
    def test_cancelling_during_the_pause_after_a_stopped_run_ends_the_animation(self):
        from tests.test_karma import fake_run
        requests, flag = [], cancel.new_flag()
        render = fake_run(requests, stop_after=[2, 3])

        def worker(req, job, timeout=None):
            result = render(req, job, timeout)
            flag.set()  # the client cancels while this run is finishing
            return result

        with (tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": home}),
              patch("hlab.karma.gpu_load", return_value=None), patch("hlab.sop_lab.worker", worker)):
            hip = Path(home) / "shot.hip"
            hip.write_bytes(b"HIP")
            started = time.monotonic()
            thread, raised = in_thread(flag, karma.animate, str(hip), "", [1, 5])
            thread.join(10)
        self.assertIsInstance(raised[0], cancel.Cancelled)
        self.assertLess(time.monotonic() - started, 5)  # not the 30 s pause
        self.assertEqual([r["frames"] for r in requests], [[1, 5]])  # and no further run


if __name__ == "__main__":
    unittest.main()
