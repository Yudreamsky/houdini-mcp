import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hlab.fx_watch import inspect, register
from hlab.storage import write


class FxWatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_actual_frames_wait_reconnect_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME":tmp}):
            root=Path(tmp)
            log=root/"husk.log"
            write(root/"manifest.json",{"title":"test","stages":[{"name":"main","kind":"xpu",
                  "first":3,"step":2,"count":2,"log":"husk.log","receipt":"exit.json"}]})
            key=register(root/"manifest.json")
            async def ask(action="status",cursor="",seconds=0):
                return await inspect(action,key,"","",0,10,cursor,seconds)
            initial=await ask()
            self.assertEqual(initial["state"],"pending")
            async def output():
                await asyncio.sleep(.10)
                (root/"0003.exr").write_bytes(b"frame")
                log.write_text("[12:00:01] Saved Image: 0003.exr\n"*2+
                               "[12:00:02] Saved Image: 0005.exr\n",encoding="utf8")
            task=asyncio.create_task(output())
            changed=await ask("wait",initial["cursor"],2)
            await task
            self.assertTrue(changed["changed"])
            self.assertEqual(changed["stages"][0]["frames_ready"],1)
            write(root/"exit.json",{"exit_code":0})
            self.assertEqual((await ask())["state"],"failed")
            (root/"0005.exr").write_bytes(b"frame")
            self.assertEqual((await ask())["state"],"complete")

    async def test_component_event_page(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"HOUDINI_RESEARCH_HOME":tmp}):
            root=Path(tmp)
            write(root/"events.json",[{"frame":81,"pair":["base","wheel_1_1"]},
                                       {"frame":109,"pair":["base","wheel_-1_1"]}])
            write(root/"manifest.json",{"title":"test","stages":[{"name":"sim","kind":"solve","count":409,
                  "log":"run.log","result":"motion.npz","receipt":"exit.json"}],
                  "events":{"path":"events.json","fps":120,"origin":78}})
            key=register(root/"manifest.json")
            page=await inspect("events",key,"","wheel_",0,1,"",0)
            self.assertEqual((page["total"],page["next_offset"],page["items"][0]["seconds_from_origin"]),(2,1,.025))
