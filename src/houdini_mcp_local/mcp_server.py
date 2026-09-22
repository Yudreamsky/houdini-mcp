"""MCP stdio process, separate from Houdini's Python and UI event loop."""

import base64
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import StrictInt

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
    return _operation('asset_ops', 'set_parameters', path, parameters)


def _operation(module, function, *args):
    code = 'import importlib\nfrom houdini_mcp_local import render_options\nimportlib.reload(render_options)\nfrom houdini_mcp_local import ' + module + '\nimportlib.reload(' + module + ')\nresult=' + module + '.' + function + '(' + ','.join(repr(a) for a in args) + ')'
    return client.call('execute_code', {'code': code})['result']


@mcp.tool(annotations=READ)
def get_capabilities() -> dict:
    """Read exact live session, supported pipelines and installed renderer nodes; availability is not a GPU render benchmark."""
    import csv, json, shutil, subprocess
    result = _operation('session_ops', 'capabilities')
    result['session_id'] = json.loads(client.session_file.read_text(encoding='utf-8'))['session_id']
    result.update(ping())
    result['gpu_probe'] = {'available': False, 'devices': [], 'verification_scope': 'device availability only; actual contribution is recorded per rendered frame'}
    executable = shutil.which('nvidia-smi')
    if executable:
        try:
            probe = subprocess.run([executable, '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            result['gpu_probe'].update(available=True, devices=[dict(name=row[0].strip(), driver=row[1].strip(), memory_mib=int(row[2].strip())) for row in csv.reader(probe.stdout.splitlines())])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
            result['gpu_probe']['error'] = str(exc)
    return result


@mcp.tool(annotations=READ)
def get_asset_schema(path: str) -> dict:
    """Inspect numeric parameter types, ranges, defaults, conditions and animation locks."""
    return _operation('asset_ops', 'get_schema', path)


@mcp.tool(annotations=WRITE)
def asset_preset(action: str, name: str = '', path: str = '', overwrite: bool = False) -> dict:
    """List, capture or apply a named numeric preset. Animated/locked/disabled channels are excluded. Exact asset type/schema required; application returns prior values and does not save the HIP."""
    return _operation('asset_ops', 'preset', action, name, path, overwrite)


def _preflight(request):
    import shutil
    from .render_jobs import validate_request, JOBS, HYTHON
    from .render_options import options, extensions
    request = dict(request, **options(request.get('renderer', 'mantra'), request.get('quality', 'preview'), request.get('sampling')))
    request.update(extensions(request['renderer'], request['width'], request['height'], request.get('region'), request.get('xpu_surface'), request.get('diagnostics')))
    validate_request(request['hip_path'], request['start_frame'], request['end_frame'], request['width'], request['height'], request.get('asset_libraries'))
    result = _operation('session_ops', 'inspect_render', request)
    free = shutil.disk_usage(JOBS if JOBS.exists() else ROOT).free
    layers = 1 + len(request['diagnostics']['aovs']) + int(request['diagnostics']['denoise'])
    estimate = request['width'] * request['height'] * (request['end_frame'] - request['start_frame'] + 1) * 32 * layers + 256 * 1024 * 1024
    result.update(disk_free_bytes=free, estimated_required_bytes=estimate)
    result['render_options'] = {k: request[k] for k in ('renderer','quality','pixel_samples','sampling','region','xpu_surface','diagnostics')}
    if request['renderer'] == 'karma_xpu' and not HYTHON.with_name('husk.exe' if os.name == 'nt' else 'husk').is_file():
        result['errors'].append('Karma husk executable is missing beside the configured hython')
        result['ready'] = False
    if free < estimate:
        result['errors'].append('Insufficient estimated disk space for preview outputs')
        result['ready'] = False
    return result


@mcp.tool(annotations=READ)
def preflight_render(hip_path: str, rop_path: str, composite_node: str, source_cop_node: str,
                     start_frame: int = 1, end_frame: int = 1, width: int = 960, height: int = 540,
                     asset_path: str = '', parameters: dict | None = None, asset_libraries: list[str] | None = None,
                     renderer: str = 'mantra', quality: str = 'preview', sampling: dict | None = None,
                     region: list[StrictInt] | None = None, xpu_surface: dict | None = None, diagnostics: dict | None = None) -> dict:
    """Read-only saved-scene/dependency validation. sampling overrides quality; Mantra pixel_samples=[x,y], paired min_rays/max_rays, noise_threshold, sample_lock, seed; XPU pixel_samples=integer. region=[left,top,right,bottom] exclusive full-frame pixels. xpu_surface selects bounded polygon/Principled physical adaptation. diagnostics accepts aovs and denoise. Reports limitations; availability is not completed-frame GPU proof."""
    return _preflight(dict(hip_path=hip_path, rop_path=rop_path, composite_node=composite_node, source_cop_node=source_cop_node, start_frame=start_frame, end_frame=end_frame, width=width, height=height, asset_path=asset_path, parameters=parameters or {}, asset_libraries=asset_libraries or [], renderer=renderer, quality=quality, sampling=sampling, region=region, xpu_surface=xpu_surface, diagnostics=diagnostics))


def _launch(identifier):
    from .render_jobs import HYTHON
    return _operation('render_jobs', 'launch_worker', identifier, str(HYTHON))


@mcp.tool(annotations=WRITE)
def render_frames(hip_path: str, rop_path: str, composite_node: str, source_cop_node: str,
                  start_frame: int = 1, end_frame: int = 1, width: int = 960, height: int = 540,
                  asset_path: str = "", parameters: dict | None = None, asset_libraries: list[str] | None = None,
                  request_id: str | None = None, renderer: str = 'mantra', quality: str = 'preview',
                  sampling: dict | None = None, region: list[StrictInt] | None = None,
                  xpu_surface: dict | None = None, diagnostics: dict | None = None) -> dict:
    """Snapshot HIP/HDA, render and record effective settings. Optional sampling/region/xpu_surface/diagnostics follow preflight_render. Defaults: Mantra 2x2/4x4, XPU 16/64. Immutable inputs include all overrides. Raw images remain separate from opt-in denoise/AOV outputs. Maximum two active jobs; inspect status and preview."""
    from .render_jobs import start_job
    return start_job(hip_path, rop_path, start_frame, end_frame, width, height, composite_node, source_cop_node, asset_path, parameters or {}, _launch, asset_libraries, request_id, _preflight, renderer, quality, sampling, region, xpu_surface, diagnostics)


@mcp.tool(annotations=WRITE)
def cancel_render(job_id: str) -> dict:
    """Request cancellation after the current frame. Does not kill Houdini or guarantee immediate stop; poll for cancelled."""
    from .render_jobs import cancel_job
    return cancel_job(job_id)


@mcp.tool(annotations=WRITE)
def resume_render(job_id: str, request_id: str | None = None) -> dict:
    """Create a child job from frozen inputs of a terminal job, reuse verified frames and rerender missing/corrupt frames. Original records are preserved. Changed dependencies reject resume."""
    from .render_jobs import resume_job
    return resume_job(job_id, _launch, request_id)


@mcp.tool(annotations=READ)
def get_render_status(job_id: str) -> dict:
    """Read durable progress, completion or failure. Partial files never imply completion. Includes only the latest frame; full evidence stays in status.json."""
    from .render_jobs import get_status
    result = get_status(job_id)
    outputs = result.pop('outputs', [])
    result['latest_output'] = outputs[-1] if outputs else None
    result['manifest_path'] = str(__import__('pathlib').Path(result['directory']) / 'status.json')
    return result


@mcp.tool(annotations=READ, structured_output=False)
def get_render_preview(job_id: str, frame: int | None = None, variant: str = 'raw') -> list[TextContent | ImageContent]:
    """Return a verified recorded PNG as native image content, with warnings, timings and GPU evidence. Defaults to the latest completed frame. Rejects missing/corrupt output; warnings are not artistic acceptance."""
    import json
    from .render_preview import read_preview
    metadata, raw = read_preview(job_id, frame, variant)
    return [TextContent(type='text', text=json.dumps(metadata)),
            ImageContent(type='image', data=base64.b64encode(raw).decode('ascii'), mimeType='image/png')]


@mcp.tool(annotations=WRITE)
def lookdev_rig(action: str, name: str = 'product', settings: dict | None = None) -> dict:
    """Inspect/capture/apply/restore an owned three-area-light, three-camera rig. apply accepts partial lights(key/fill/rim) and cameras(hero/reference/detail); returns a conflict-checked restore_token. restore settings={restore_token:...}. Does not save HIP. Defaults are uncalibrated design starting points, never silently replace existing scene lights."""
    return _operation('lookdev_rig', 'operate', action, name, settings)


@mcp.tool(annotations=READ)
def compare_render_jobs(job_ids: list[str], frame: int | None = None) -> dict:
    """Compare 2-8 verified raw previews of identical scene/camera/region/backend, allowing only sampling changes. Returns local noise proxy, adjacent MAE and measured timing; no automatic claim of convergence or artistic acceptance."""
    from .render_comparison import compare
    return compare(job_ids, frame)


@mcp.tool(annotations=READ)
def list_procedural_assets() -> dict:
    """List implemented recipes, units, numeric types/bounds and structured cross-parameter constraints. No scene changes."""
    return _operation('procedural_assets', 'catalog')


@mcp.tool(annotations=WRITE)
def upsert_asset_instance(instance_id: str, parameters: dict | None = None, recipe: str | None = None) -> dict:
    """Create/update an owned HDA instance. Omitted recipe infers an existing instance's recipe; a new instance defaults to pipe_support_sample. Other recipes: pipe_elbow_sample, pipe_rack_sample, pipe_rack_reference, external_coupling_sample, pipe_rack_coupled. Explicit recipe mismatch, animation, unlocked content and implicit version migration are rejected. Does not save."""
    return _operation('procedural_assets', 'upsert', instance_id, parameters or {}, recipe)


@mcp.tool(annotations=READ)
def preflight_asset_instance(instance_id: str, parameters: dict | None = None, recipe: str | None = None) -> dict:
    """Read-only combined-parameter and instance/channel validation. Returns ready, structured violations, merged proposed values and inferred recipe. No HDA compilation, installation, node creation, parameter writes or cook. Geometry is checked by upsert; preflight is not a reservation."""
    return _operation('procedural_assets', 'preflight', instance_id, parameters or {}, recipe)


@mcp.tool(annotations=READ)
def inspect_asset_instance(path: str) -> dict:
    """Inspect actual sample geometry: per-part IDs, bounds, closed edges, selected dimensions and support interfaces. Local-space checks, not a general collision or structural certification tool."""
    return _operation('sample_inspection', 'inspect', path)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False), structured_output=False)
def preview_asset_views(path: str, views: list[str] | None = None, width: int = 960, height: int = 540, part_types: list[str] | None = None, part_names: list[str] | None = None) -> list[TextContent | ImageContent]:
    """Capture front/right/top/perspective views of an owned sample, returning native PNG images. Exact part_names optionally isolate and frame 1-128 components; combined filters intersect and empty selections fail. Requires GUI. Temporarily changes viewport settings and restores them. This is geometry review, not material/render acceptance."""
    import json
    result = _operation('sample_views', 'capture', path, views or ['front','right','top','perspective'], width, height, part_types, part_names)
    content = []
    for item in result['views']:
        data = item.pop('image_base64')
        content.extend([TextContent(type='text', text=json.dumps(item)),ImageContent(type='image',data=data,mimeType='image/png')])
    content.append(TextContent(type='text',text=json.dumps({k:v for k,v in result.items() if k!='views'})))
    return content


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
