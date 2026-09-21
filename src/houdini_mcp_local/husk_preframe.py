"""Executed by husk before every frame. Skip remaining frames on cancellation."""
import json
import os
import sys
import time
from pathlib import Path
import hou

sys.path.insert(0, os.environ['WORKAI_RENDER_SOURCE'])
from houdini_mcp_local.io_utils import atomic_json
from houdini_mcp_local.render_jobs import alive

class SkipFrame(Exception):
    pass

folder = Path(os.environ['WORKAI_RENDER_JOB'])
owner = json.loads((folder / 'worker-owner.json').read_text(encoding='utf-8'))
if (folder / 'cancel.json').exists() or alive(owner['pid'], owner.get('created')) is False:
    atomic_json(folder / 'renderer-stop.json', {'frame': int(hou.frame()), 'at': time.perf_counter(),
                                              'reason': 'cancel_requested' if (folder / 'cancel.json').exists() else 'owner_exited'})
    raise SkipFrame('Cancellation or exited worker; skip remaining frames')
atomic_json(folder / f'start_{int(hou.frame()):04}.json', {'frame': int(hou.frame()), 'at': time.perf_counter()})
