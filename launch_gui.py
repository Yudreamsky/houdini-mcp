"""Launch a dedicated interactive Houdini using per-process plugin paths."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import socket

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--houdini", default=r"C:\Program Files\Side Effects Software\Houdini 20.5.487\bin\houdinifx.exe")
parser.add_argument("--hip")
args = parser.parse_args()
runtime = ROOT / ".runtime"
runtime.mkdir(exist_ok=True)
descriptor = runtime / "gui-session.json"
if descriptor.exists():
    current = json.loads(descriptor.read_text(encoding="utf-8"))
    if current.get("host") != "127.0.0.1":
        raise SystemExit("Unexpected session host; inspect the descriptor before launching.")
    try:
        with socket.create_connection((current["host"], current["port"]), timeout=0.5):
            pass
    except OSError:
        pass
    else:
        raise SystemExit(f"A bridge session is already running (PID {current['pid']}). Close it before launching another.")
env = os.environ.copy()
env["WORKAI_HOUDINI_MCP"] = "1"
env["WORKAI_HOUDINI_MCP_ROOT"] = str(ROOT)
env["HOUDINI_MCP_SESSION_FILE"] = str(runtime / "gui-session.json")
env["HOUDINI_PATH"] = str(ROOT / "houdini") + os.pathsep + env.get("HOUDINI_PATH", "&")
env["HOUDINI_USER_PREF_DIR"] = str(runtime / "houdini20.5")
Path(env["HOUDINI_USER_PREF_DIR"]).mkdir(exist_ok=True)
command = [args.houdini]
if args.hip:
    command.append(str(Path(args.hip).resolve()))
with (runtime / "gui.stdout.log").open("ab") as stdout, (runtime / "gui.stderr.log").open("ab") as stderr:
    process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=stdout, stderr=stderr)
print(json.dumps({"launched_pid": process.pid, "session_file": env["HOUDINI_MCP_SESSION_FILE"]}))
