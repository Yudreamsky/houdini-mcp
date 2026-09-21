from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from houdini_mcp_local.houdini_backend import run_headless

if __name__ == "__main__":
    run_headless(sys.argv[1])
