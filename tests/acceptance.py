"""Real MCP stdio -> local bridge -> installed Houdini acceptance, no mock hou."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence" / ("headless-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
SESSION = ROOT / ".runtime" / (RUN.name + ".json")
HYTHON = Path(os.environ.get("HOUDINI_HYTHON", r"C:\Program Files\Side Effects Software\Houdini 20.5.487\bin\hython.exe"))
REPORT = {"started_at": datetime.now().isoformat(), "mode": "headless", "checks": []}


async def main():
    RUN.mkdir(parents=True)
    with (RUN / "houdini.stdout.log").open("wb") as stdout, (RUN / "houdini.stderr.log").open("wb") as stderr:
        process = subprocess.Popen([str(HYTHON), str(ROOT / "run_headless.py"), str(SESSION)],
                                   cwd=ROOT, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 120
            while not SESSION.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"Houdini exited early: {process.returncode}")
                if time.monotonic() > deadline:
                    raise TimeoutError("Houdini startup exceeded 120 seconds")
                await asyncio.sleep(0.25)
            env = os.environ.copy()
            env["HOUDINI_MCP_SESSION_FILE"] = str(SESSION)
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "run_mcp.py")], env=env)
            with (RUN / "mcp.stderr.log").open("w", encoding="utf-8") as errors:
                async with stdio_client(params, errlog=errors) as streams:
                    async with ClientSession(*streams) as client:
                        initialized = await client.initialize()
                        REPORT["server"] = initialized.serverInfo.model_dump()

                        async def call(name, arguments=None, error=False):
                            response = await client.call_tool(name, arguments or {})
                            record = {"tool": name, "is_error": bool(response.isError)}
                            if response.structuredContent:
                                result = response.structuredContent
                            else:
                                texts = [item.text for item in response.content if item.type == "text"]
                                try:
                                    result = json.loads(texts[0]) if len(texts) == 1 else texts
                                except ValueError:
                                    result = texts
                            record["result"] = result
                            REPORT["checks"].append(record)
                            assert bool(response.isError) == error, record
                            return result

                        listed = await client.list_tools()
                        names = {tool.name for tool in listed.tools}
                        expected = {"ping", "get_scene_info", "get_node_info", "execute_code", "save_scene", "open_scene", "get_viewport_screenshot"}
                        assert names == expected, names
                        REPORT["tools"] = sorted(names)
                        ping = await call("ping")
                        assert ping["version"] == "20.5.487" and ping["ui_available"] is False
                        await call("get_scene_info")
                        built = await call("execute_code", {"code": """
geo = hou.node('/obj').createNode('geo', 'mcp_acceptance')
sphere = geo.createNode('sphere', 'source_sphere')
sphere.parm('type').set(1)
sphere.parmTuple('rad').set((1.0, 1.0, 1.0))
xform = geo.createNode('xform', 'offset')
xform.setInput(0, sphere)
xform.parmTuple('t').set((2.0, 0.0, 0.0))
out = geo.createNode('null', 'OUT')
out.setInput(0, xform)
out.setDisplayFlag(True)
out.setRenderFlag(True)
geo.layoutChildren()
print('Houdini MCP: 球体创建完成')
result = {'path': out.path(), 'points': out.geometry().intrinsicValue('pointcount')}
"""})
                        assert built["result"]["points"] > 0
                        measured = await call("get_node_info", {"path": "/obj/mcp_acceptance/OUT", "geometry": True})
                        assert measured["geometry"]["bbox_min"][0] >= 0.9
                        await call("execute_code", {"code": "hou.node('/obj/mcp_acceptance/offset').parmTuple('t').set((3,0,0)); result = 3"})
                        inspected = await call("get_node_info", {"path": "/obj/mcp_acceptance/offset", "parameters": ["t"]})
                        assert inspected["parameters"]["t"] == [3.0, 0.0, 0.0]
                        saved = await call("save_scene", {"path": str(RUN / "acceptance.hip")})
                        assert saved["bytes"] > 0
                        await call("save_scene", {"path": saved["path"]}, error=True)
                        await call("execute_code", {"code": "raise ValueError('expected test error')"}, error=True)
                        await call("get_node_info", {"path": "/obj/nonexistent"}, error=True)
                        await call("execute_code", {"code": "hou.node('/obj/mcp_acceptance/offset').parmTuple('t').set((99,0,0))"})
                        await call("open_scene", {"path": saved["path"]}, error=True)
                        await call("open_scene", {"path": saved["path"], "discard_unsaved": True})
                        reopened = await call("get_node_info", {"path": "/obj/mcp_acceptance/offset", "parameters": ["t"]})
                        assert reopened["parameters"]["t"] == [3.0, 0.0, 0.0]
                        remeasured = await call("get_node_info", {"path": "/obj/mcp_acceptance/OUT", "geometry": True})
                        assert remeasured["geometry"]["points"] == measured["geometry"]["points"]
                        await call("get_viewport_screenshot", error=True)
                        REPORT["passed"] = True
        except BaseException as exc:
            REPORT["passed"] = False
            REPORT["failure"] = repr(exc)
            raise
        finally:
            # Only terminate this test's dedicated child process.
            process.terminate()
            process.wait(timeout=15)
            SESSION.unlink(missing_ok=True)
            REPORT["finished_at"] = datetime.now().isoformat()
            (RUN / "report.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"passed": REPORT.get("passed"), "checks": len(REPORT["checks"]), "report": str(RUN / "report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
