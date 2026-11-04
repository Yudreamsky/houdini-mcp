"""Check the published mechanical examples through stdio, with an empty local library."""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="houdini-mechanisms-test-") as folder:
        params = StdioServerParameters(command=sys.executable, args=[str(root / "run_mcp.py")],
                                       cwd=folder, env=dict(os.environ, HOUDINI_RESEARCH_HOME=folder))
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
            await client.initialize()
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert {"window_session", "mechanical_rig", "mechanism", "animation_gap"} <= names

            async def call(name, **arguments):
                result = await client.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError(result.content[0].text)
                return result.structuredContent or json.loads(result.content[0].text)

            listing = await call("knowledge", topic="mechanical-animation", kind="mechanism_test")
            assert listing["total"] == 4
            for card in listing["cards"]:
                detail = (await call("knowledge", key=card["id"]))["details"]
                scene = root / "examples" / detail["hip"].removeprefix("sample:")
                assert hashlib.sha256(scene.read_bytes()).hexdigest() == detail["sha256"], scene
            report = await call("animation_gap", hip="sample:mechanisms/Climbing-support-transfer.hip",
                                upper="/obj/CLIMBING_STUDY/New_section", lower="/obj/CLIMBING_STUDY/Cart",
                                start=1379, end=1454, minimum=0.228)
            assert report["status"] == "passed" and report["measured_frames"] == 76
            assert abs(report["lowest"]["gap"] - 0.230) < 1e-5
            print(f'{len(names)} tools, 4 bundled cases, 76 frames, minimum gap {report["lowest"]["gap"]:.6f}')


if __name__ == "__main__":
    asyncio.run(check())
