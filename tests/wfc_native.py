"""Fresh MCP -> saved request -> editable HIP -> mesh checks, without opening a GUI or rendering."""

import argparse
from pathlib import Path
import subprocess
import sys

from hlab.runtime import discover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    files = [output / name for name in ("maze.json", "Maze.hip", "native-verification.json")]
    if any(path.exists() for path in files):
        raise FileExistsError("Use a new output directory for this acceptance run")
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    hython = str(discover().hython)
    commands = [
        [sys.executable, str(root / "examples/wfc/run.py"), "maze", "--seed", "4", "--output", str(files[0])],
        [hython, str(root / "examples/wfc/build_houdini.py"), str(files[0]), "--output", str(files[1])],
        [hython, str(root / "tests/wfc_native_check.py"), str(files[1]), str(files[2])],
    ]
    for command in commands:
        subprocess.run(command, cwd=root, check=True)
    print(f"Verified: {files[2]}")


if __name__ == "__main__":
    main()
