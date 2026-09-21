"""Houdini 20.5 scene-load entry point; start() is idempotent after reopening."""
import os
import sys
from pathlib import Path

if os.environ.get("WORKAI_HOUDINI_MCP") == "1":
    project = Path(os.environ["WORKAI_HOUDINI_MCP_ROOT"])
    sys.path.insert(0, str(project / "src"))
    from houdini_mcp_local.houdini_backend import start
    start(os.environ["HOUDINI_MCP_SESSION_FILE"])
