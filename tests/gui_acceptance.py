"""Complete the visual feedback loop in the dedicated GUI acceptance scene."""
import argparse
import asyncio
import base64
from datetime import datetime
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--pid", type=int, required=True)
parser.add_argument("--source-hip", required=True)
args = parser.parse_args()
RUN = ROOT / "evidence" / ("gui-" + datetime.now().strftime("%Y%m%d-%H%M%S"))


async def main():
    RUN.mkdir(parents=True)
    report = {"checks": [], "expected_pid": args.pid}
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "run_mcp.py")], env=os.environ.copy())
    try:
        with (RUN / "mcp.stderr.log").open("w", encoding="utf-8") as errors:
            async with stdio_client(params, errlog=errors) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()

                    async def call(name, values=None):
                        response = await client.call_tool(name, values or {})
                        assert not response.isError, response
                        data = response.structuredContent
                        if data is None:
                            texts = [item.text for item in response.content if item.type == "text"]
                            data = json.loads(texts[0]) if len(texts) == 1 else texts
                        report["checks"].append({"tool": name, "result": data})
                        return response, data

                    _, info = await call("ping")
                    assert info["pid"] == args.pid and info["ui_available"] is True, info
                    assert (ROOT / "evidence").resolve() in Path(info["hip_path"]).resolve().parents
                    source = Path(args.source_hip).resolve()
                    assert source.name == "acceptance.hip" and (ROOT / "evidence").resolve() in source.parents
                    await call("open_scene", {"path": str(source)})
                    await call("get_scene_info")
                    await call("execute_code", {"code": """
sphere = hou.node('/obj/mcp_acceptance/source_sphere')
assert sphere is not None
sphere.parmTuple('rad').set((1.25, 1.25, 1.25))
geo = sphere.parent()
color = geo.createNode('color', 'preview_color')
color.setInput(0, hou.node('/obj/mcp_acceptance/offset'))
color.parmTuple('color').set((0.02, 0.45, 1.0))
hou.node('/obj/mcp_acceptance/OUT').setInput(0, color)
geo.layoutChildren()
viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
viewer.setPwd(hou.node('/obj'))
viewer.referencePlane().setIsVisible(False)
viewer.curViewport().frameBoundingBox(hou.BoundingBox(1,-2,-2,5,2,2))
for guide in (hou.viewportGuide.XYPlane, hou.viewportGuide.XZPlane, hou.viewportGuide.YZPlane, hou.viewportGuide.ObjectSelection):
    viewer.curViewport().settings().enableGuide(guide, False)
result = {'radius': list(sphere.parmTuple('rad').eval()), 'color': list(color.parmTuple('color').eval())}
"""})
                    response, metadata = await call("get_viewport_screenshot", {"width": 960, "height": 540})
                    images = [item for item in response.content if item.type == "image"]
                    assert len(images) == 1, [item.type for item in response.content]
                    assert response.structuredContent is None, "Image must not be duplicated as JSON base64"
                    image_path = RUN / "viewport.png"
                    image_path.write_bytes(base64.b64decode(images[0].data))
                    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                    report["screenshot"] = str(image_path)
                    _, saved = await call("save_scene", {"path": str(RUN / "gui-acceptance.hip")})
                    await call("open_scene", {"path": saved["path"]})
                    _, node = await call("get_node_info", {"path": "/obj/mcp_acceptance/source_sphere", "parameters": ["rad"]})
                    assert node["parameters"]["rad"] == [1.25, 1.25, 1.25]
                    report["passed"] = True
    except BaseException as exc:
        report["passed"] = False
        report["failure"] = repr(exc)
        raise
    finally:
        (RUN / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "report": str(RUN / "report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
