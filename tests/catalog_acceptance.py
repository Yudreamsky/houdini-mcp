"""Check progressive discovery and unlisted compatibility calls through a fresh MCP client."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="houdini-catalog-") as temp:
        opts = StdioServerParameters(
            command=sys.executable,
            args=[str(root / "run_mcp.py")],
            cwd=temp,
            env=dict(os.environ, HOUDINI_RESEARCH_HOME=temp),
        )
        async with stdio_client(opts) as (rd, wr), ClientSession(rd, wr) as c:
            await c.initialize()
            shown = {t.name for t in (await c.list_tools()).tools}
            assert "domain_recipe" in shown and len(shown) <= 17 and "animation_gap" not in shown
            item = await c.call_tool("domain_recipe", {"name": "animation_gap"})
            assert not item.isError and "axis" in item.structuredContent["inputSchema"]["properties"]
            args = dict(
                hip="sample:mechanisms/Climbing-support-transfer.hip",
                upper="/obj/CLIMBING_STUDY/New_section",
                lower="/obj/CLIMBING_STUDY/Cart",
                start=1379,
                end=1379,
                minimum=0.228,
            )
            old = await c.call_tool("animation_gap", args)
            new = await c.call_tool(
                "domain_recipe", dict(action="run", name="animation_gap", arguments=args)
            )
            assert not old.isError and not new.isError, (old.content, new.content)
            assert old.structuredContent == new.structuredContent and old.content == new.content
            bad = await c.call_tool(
                "domain_recipe", dict(action="run", name="animation_gap", arguments={**args, "start": "1"})
            )
            assert bad.isError and "integer" in bad.content[0].text
            print(
                f"{len(shown)} default tools; schema, compatibility call and strict routed call verified."
            )


if __name__ == "__main__":
    asyncio.run(check())
