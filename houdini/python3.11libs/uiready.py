import os
import sys

if os.environ.get("HOUDINI_RESEARCH_ROOT"):
    sys.path.insert(0, os.environ["HOUDINI_RESEARCH_ROOT"])
    from hlab.host import start
    start()
