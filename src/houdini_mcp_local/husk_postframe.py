"""Executed only after husk saves this frame; publish an atomic completion receipt."""
import os
import sys
import time
from pathlib import Path
import hou

sys.path.insert(0, os.environ['WORKAI_RENDER_SOURCE'])
from houdini_mcp_local.io_utils import atomic_json

folder = Path(os.environ['WORKAI_RENDER_JOB'])
atomic_json(folder / f'ready_{int(hou.frame()):04}.json', {'frame': int(hou.frame()), 'at': time.perf_counter()})
