"""MCP stdio process, separate from Houdini's Python and UI event loop."""

import base64
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations

from .protocol import HoudiniClient

ROOT = Path(__file__).resolve().parents[2]
client = HoudiniClient(os.environ.get("HOUDINI_MCP_SESSION_FILE", str(ROOT / ".runtime" / "gui-session.json")))
mcp = FastMCP("workai-houdini", instructions=(
    "Inspect ping and get_scene_info before editing. Calls operate on the exact Houdini session in the descriptor. "
    "execute_code is trusted arbitrary Python, not a sandbox. Save a version before significant changes; errors can leave partial edits. "
    "After an uncertain timeout, inspect before retrying. Use screenshots for visual evidence and save/reopen for persistence. "
    "Use existing nodes where possible. Build small reusable assets; add specialized tools when repeated work justifies them."
))
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


@mcp.tool(annotations=READ)
def ping() -> dict:
    """Verify the active Houdini version, PID, UI availability and current hip path."""
    from . import __version__
    result = client.call("ping")
    result['mcp_server_version'] = __version__
    return result


@mcp.tool(annotations=READ)
def get_scene_info(path: str = "/obj", limit: int = 100) -> dict:
    """Read the current scene and bounded child node list. Does not recursively cook geometry."""
    return client.call("get_scene_info", {"path": path, "limit": limit})


@mcp.tool(annotations=READ)
def get_node_info(path: str, parameters: list[str] | None = None, geometry: bool = False) -> dict:
    """Inspect a node, inputs, errors and named parameter tuples; optionally cook and measure SOP geometry."""
    return client.call("get_node_info", {"path": path, "parameters": parameters or [], "geometry": geometry})


@mcp.tool(annotations=WRITE)
def execute_code(code: str) -> dict:
    """Run Python with hou on Houdini's main thread. Set result to JSON data; stdout is captured. No automatic rollback."""
    return client.call("execute_code", {"code": code})


@mcp.tool(annotations=WRITE)
def save_scene(path: str, overwrite: bool = False) -> dict:
    """Save to an absolute hip path and verify non-empty output and SHA256. Existing files need explicit overwrite."""
    return client.call("save_scene", {"path": path, "overwrite": overwrite})


@mcp.tool(annotations=WRITE)
def open_scene(path: str, discard_unsaved: bool = False) -> dict:
    """Open a hip file and return current scene evidence. Refuse unsaved changes unless explicitly allowed."""
    return client.call("open_scene", {"path": path, "discard_unsaved": discard_unsaved})


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False), structured_output=False)
def get_viewport_screenshot(width: int = 960, height: int = 540) -> list[TextContent | ImageContent]:
    """Capture the current Scene Viewer as a PNG and return native MCP image content. Requires GUI."""
    import json
    result = client.call("get_viewport_screenshot", {"width": width, "height": height})
    data = result.pop("image_base64")
    # Validate the payload before forwarding it as a native image.
    if not base64.b64decode(data).startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Screenshot is not a PNG")
    return [TextContent(type="text", text=json.dumps(result)),
            ImageContent(type="image", data=data, mimeType="image/png")]


@mcp.tool(annotations=WRITE)
def set_asset_parameters(path: str, parameters: dict) -> dict:
    """Set numeric asset parameters after validating the entire request. Refuses animated channels. Does not save."""
    import json
    code = "from houdini_mcp_local.asset_ops import set_parameters\nresult = set_parameters(" + repr(path) + ", " + repr(parameters) + ")"
    return client.call("execute_code", {"code": code})


@mcp.tool(annotations=WRITE)
def render_frames(hip_path: str, rop_path: str, composite_node: str, source_cop_node: str,
                  start_frame: int = 1, end_frame: int = 1, width: int = 960, height: int = 540,
                  asset_path: str = "", parameters: dict | None = None, asset_libraries: list[str] | None = None) -> dict:
    """Start a durable background Mantra+COP2 preview job from a saved HIP snapshot. Returns job id, not completion. Use get_render_status. GUI edits not saved to HIP are excluded. Outputs go to a unique job folder."""
    from .render_jobs import start_job, HYTHON
    def launch(identifier):
        code = "import importlib\nimport houdini_mcp_local.render_jobs as jobs\nimportlib.reload(jobs)\nresult=jobs.launch_worker(" + repr(identifier) + ", " + repr(str(HYTHON)) + ")"
        return client.call('execute_code', {'code': code})
    return start_job(hip_path, rop_path, start_frame, end_frame, width, height, composite_node, source_cop_node, asset_path, parameters or {}, launch, asset_libraries)


@mcp.tool(annotations=READ)
def get_render_status(job_id: str) -> dict:
    """Read durable progress, completion or failure. Partial files never imply completion. Includes only the latest frame; full evidence stays in status.json."""
    from .render_jobs import get_status
    result = get_status(job_id)
    outputs = result.pop('outputs', [])
    result['latest_output'] = outputs[-1] if outputs else None
    result['manifest_path'] = str(__import__('pathlib').Path(result['directory']) / 'status.json')
    return result


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
