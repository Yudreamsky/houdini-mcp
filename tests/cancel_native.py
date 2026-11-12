"""Run python -m tests.cancel_native on this machine. A real MCP client starts a long Karma render; while it renders
the server answers other tools; cancelling the call ends the renderer within seconds and the next render works; and
closing the connection during a render ends the renderer too. Skips when other programs hold the GPU."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, McpError, StdioServerParameters, types
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
SLOW = {"samples": 16384, "denoiser": "off", "max_edge": 1920, "time_limit": 120}


def renderers():
    listed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq husk.exe", "/NH"], capture_output=True)
    return listed.stdout.decode(errors="replace").lower().count("husk.exe")


async def until(condition, seconds):
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if condition():
            return round(time.monotonic() - started, 1)
        await asyncio.sleep(.25)
    return None


async def accept(home):
    from hlab import karma
    busiest = max((karma.gpu_load() or {}).get("utilization_percent", 0) for _ in range(3))
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    idle = renderers()
    env = dict(os.environ, HOUDINI_RESEARCH_HOME=home, HOUDINI_RESEARCH_WORKER="warm")
    server = StdioServerParameters(command=sys.executable, args=[str(REPO / "run_mcp.py")], env=env, cwd=str(REPO))
    seconds = {}
    async with stdio_client(server) as (rd, wr), ClientSession(rd, wr) as client:
        await client.initialize()

        async def karma_tool(**arguments):
            result = await client.call_tool("domain_recipe", {"action": "run", "name": "karma", "arguments": arguments})
            text = next(c.text for c in result.content if c.type == "text")
            assert not result.isError, text
            return json.loads(text)

        async def timed(label, tool, **arguments):
            started = time.monotonic()
            result = await client.call_tool(tool, arguments)
            seconds[label] = round(time.monotonic() - started, 2)
            assert not result.isError, result.content

        first = await karma_tool(action="render", hip="karma-probe", changes={"max_edge": 640})
        assert first["status"] == "completed", first["notes"]

        request = client._request_id  # the id the next request gets; the client has no public way to cancel
        long = asyncio.create_task(karma_tool(action="render", hip="karma-probe", changes=SLOW))
        assert await until(lambda: renderers() > idle, 90) is not None, "the long render never started husk"
        # The server answers while the render runs.
        await timed("knowledge", "knowledge", topic="render")
        await timed("window list", "window_session", action="list")
        await timed("catalog", "domain_recipe", action="catalog")
        await timed("presets", "domain_recipe", action="run", name="karma", arguments={"action": "presets"})
        assert max(seconds.values()) < 3 and not long.done() and renderers() > idle, seconds
        # Cancelling the call ends husk and the worker that started it.
        await client.send_notification(types.ClientNotification(types.CancelledNotification(
            params=types.CancelledNotificationParams(requestId=request, reason="acceptance test"))))
        try:
            await asyncio.wait_for(long, 30)
            raise AssertionError("the cancelled render returned a result")
        except McpError as exc:
            assert "cancel" in str(exc).lower(), exc
        seconds["renderer gone after cancel"] = await until(lambda: renderers() == idle, 20)
        assert seconds["renderer gone after cancel"] is not None, "husk kept rendering after the cancel"
        # The worker starts again for the next render.
        again = await karma_tool(action="render", hip="karma-probe", changes={"max_edge": 640})
        assert again["status"] == "completed", again["notes"]

        # Closing the connection during a render ends it as well.
        asyncio.create_task(karma_tool(action="render", hip="karma-probe", changes=SLOW))
        assert await until(lambda: renderers() > idle, 90) is not None, "the second long render never started husk"
    seconds["renderer gone after disconnect"] = await until(lambda: renderers() == idle, 20)
    assert seconds["renderer gone after disconnect"] is not None, "husk kept rendering after the client left"
    print("PASS a render no longer blocks the server: other tools answered during it, cancel and disconnect ended husk:",
          seconds)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="cancel-acceptance-", ignore_cleanup_errors=True) as tmp:
        asyncio.run(accept(tmp))
