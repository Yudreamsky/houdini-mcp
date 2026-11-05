"""Run python -m tests.karma_runtime_native to check warm-worker frames through the MCP render route."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def fixture(path):
    from hlab.karma_render import build_sample
    build_sample(path)


def check_readonly_frames(path):
    import hou
    from hlab.animation_gap import measure_frames
    from hlab.sop_worker import work

    hou.hipFile.load(str(path), suppress_save_prompt=True)
    hou.setFrame(4.5)
    gap = dict(upper="/obj/BALL", lower="/obj/GROUND", axis="y", start=2, end=9,
               minimum=None, maximum=None)
    assert measure_frames(gap)["measured_frames"] == 8
    assert hou.frame() == 4.5, "gap inspection changed the entering frame"
    with patch("hlab.animation_gap.axis_bounds", side_effect=RuntimeError("probe failure")):
        try:
            measure_frames(gap)
        except RuntimeError as exc:
            assert str(exc) == "probe failure"
        else:
            raise AssertionError("expected the injected geometry failure")
    assert hou.frame() == 4.5, "failed gap inspection changed the entering frame"

    for action, node in (("nodes", "/obj/BOX"), ("inspect", "/obj/BOX/box1")):
        req = dict(action=action, node=node, frame=12, query="", offset=0, limit=10)
        result = work(req, path.parent, load=False)
        assert result["items"], result
        assert hou.frame() == 4.5, f"{action} changed the entering frame"
        try:
            work({**req, "node": "/obj/MISSING"}, path.parent, load=False)
        except ValueError:
            pass
        else:
            raise AssertionError("expected missing node to fail")
        assert hou.frame() == 4.5, f"failed {action} changed the entering frame"


async def accept(path):
    from hlab.server import mcp
    from hlab.storage import sha

    async def call(name, arguments):
        result = await mcp.call_tool("domain_recipe", {"action": "run", "name": name, "arguments": arguments})
        if result.isError:
            raise AssertionError(result)
        return json.loads(next(row.text for row in result.content if row.type == "text"))

    before = sha(path)
    gap = await call("animation_gap", {"hip": str(path), "upper": "/obj/BALL", "lower": "/obj/GROUND",
                                       "start": 2, "end": 9})
    assert gap["measured_frames"] == 8
    args = {"action": "render", "hip": str(path),
            "changes": {"engine": "cpu", "denoiser": "off", "width": 64, "samples": 1}}
    first = await call("karma", args)
    second = await call("karma", args)
    assert [first["frame"], second["frame"]] == [1, 1], (first["frame"], second["frame"])
    for run in (first, second):
        assert run["status"] == "completed" and run["hip_unchanged"], run
        assert run["resolution"] == [64, 36], run
    assert sha(path) == before
    print("PASS normal MCP route: gap F2-9 then two default renders both use saved F1; HIP unchanged")


def main():
    from hlab.runtime import discover
    from hlab.worker_pool import pool

    with tempfile.TemporaryDirectory(prefix="karma-runtime-native-") as tmp:
        folder = Path(tmp)
        path = folder / "source.hip"
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            subprocess.run([str(discover().hython), "-m", "tests.karma_runtime_native", "fixture", str(path)],
                           check=True, timeout=120)
            try:
                asyncio.run(accept(path))
            finally:
                pool.close()
            subprocess.run([str(discover().hython), "-m", "tests.karma_runtime_native", "readonly", str(path)],
                           check=True, timeout=120)
    print("PASS read-only frame restoration on success and failure (gap, nodes, inspect)")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        (fixture if sys.argv[1] == "fixture" else check_readonly_frames)(Path(sys.argv[2]))
    else:
        main()
