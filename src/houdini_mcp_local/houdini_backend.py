"""Houdini operations. Imported only inside Houdini / hython."""

import base64
import contextlib
import hashlib
import io
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path

import hou

from . import __version__
from .service import LocalService

_service = None


def node_summary(node):
    return {"path": node.path(), "type": node.type().name(),
            "category": node.type().category().name(), "name": node.name()}


def file_info(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty output not found: {path}")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def absolute_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Use an absolute file path")
    return path.resolve()


def dispatch(command, params):
    if command == "ping":
        return {"version": hou.applicationVersionString(), "bridge_version": __version__,
                "pid": os.getpid(), "ui_available": hou.isUIAvailable(),
                "hip_path": hou.hipFile.path(), "python": sys.version.split()[0]}
    if command == "get_scene_info":
        node = hou.node(params.get("path", "/obj"))
        if node is None:
            raise ValueError("Node path does not exist")
        limit = max(1, min(int(params.get("limit", 100)), 1000))
        children = node.children()
        return {"hip_path": hou.hipFile.path(), "unsaved_changes": hou.hipFile.hasUnsavedChanges(),
                "frame": hou.frame(), "fps": hou.fps(), "path": node.path(),
                "children": [node_summary(n) for n in children[:limit]],
                "child_count": len(children), "truncated": len(children) > limit,
                "selected": [n.path() for n in hou.selectedNodes()][:100]}
    if command == "get_node_info":
        node = hou.node(params["path"])
        if node is None:
            raise ValueError("Node path does not exist")
        result = node_summary(node)
        result.update({"inputs": [n.path() if n else None for n in node.inputs()],
                       "errors": list(node.errors()) if hasattr(node, "errors") else [],
                       "warnings": list(node.warnings()) if hasattr(node, "warnings") else []})
        result["parameters"] = {}
        for name in params.get("parameters", []):
            parm = node.parmTuple(name)
            if parm is None:
                raise ValueError(f"Parameter does not exist: {name}")
            result["parameters"][name] = list(parm.eval())
        if params.get("geometry", False):
            if not isinstance(node, hou.SopNode):
                raise ValueError("Geometry inspection requires a SOP node")
            geo = node.geometry()
            if geo is None:
                raise RuntimeError("Node has no geometry")
            box = geo.boundingBox()
            result["geometry"] = {"points": geo.intrinsicValue("pointcount"),
                                  "primitives": geo.intrinsicValue("primitivecount"),
                                  "bbox_min": list(box.minvec()), "bbox_max": list(box.maxvec()),
                                  "point_attributes": [a.name() for a in geo.pointAttribs()]}
        return result
    if command == "execute_code":
        code = params["code"]
        if not isinstance(code, str) or len(code) > 200000:
            raise ValueError("code must be a string of at most 200000 characters")
        namespace = {"hou": hou, "__name__": "__houdini_mcp__"}
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), hou.undos.group("WORKAI MCP"):
                exec(compile(code, "<houdini_mcp>", "exec"), namespace)
            result = namespace.get("result")
            json.dumps(result, allow_nan=False)
        except BaseException as exc:
            raise RuntimeError(
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-8000:]}\n"
                f"stdout: {stdout.getvalue()[-4000:]}\nPartial changes may remain; inspect before retrying."
            ) from exc
        return {"executed": True, "result": result, "stdout": stdout.getvalue()[:16000],
                "stderr": stderr.getvalue()[:8000],
                "stdout_truncated": len(stdout.getvalue()) > 16000}
    if command == "save_scene":
        path = absolute_path(params["path"])
        if path.suffix.lower() not in (".hip", ".hiplc", ".hipnc"):
            raise ValueError("Scene extension must be .hip, .hiplc or .hipnc")
        if path.exists() and not params.get("overwrite", False):
            raise FileExistsError("File exists; use another path or explicitly set overwrite=True")
        path.parent.mkdir(parents=True, exist_ok=True)
        hou.hipFile.save(str(path), save_to_recent_files=False)
        actual = absolute_path(hou.hipFile.path())
        result = file_info(actual)
        result["requested_path"] = str(path)
        return result
    if command == "open_scene":
        path = absolute_path(params["path"])
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if hou.hipFile.hasUnsavedChanges() and not params.get("discard_unsaved", False):
            raise RuntimeError("Current scene has unsaved changes; save it or explicitly allow discarding")
        warning = None
        try:
            hou.hipFile.load(str(path), suppress_save_prompt=True)
        except hou.LoadWarning as exc:
            warning = str(exc)
        if absolute_path(hou.hipFile.path()) != path:
            raise RuntimeError("Houdini current path does not match the requested file")
        return {"opened": str(path), "warning": warning, "scene": dispatch("get_scene_info", {})}
    if command == "get_viewport_screenshot":
        if not hou.isUIAvailable():
            raise RuntimeError("Viewport screenshots require a graphical Houdini session; headless is not supported")
        viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            raise RuntimeError("No Scene Viewer pane is available")
        width = max(128, min(int(params.get("width", 960)), 1920))
        height = max(128, min(int(params.get("height", 540)), 1080))
        output_dir = _service.session_file.parent / "captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"viewport-{uuid.uuid4().hex}.png"
        settings = viewer.flipbookSettings().stash()
        settings.frameRange((hou.frame(), hou.frame()))
        settings.outputToMPlay(False)
        settings.output(str(path))
        settings.useResolution(True)
        settings.resolution((width, height))
        viewer.flipbook(viewer.curViewport(), settings)
        info = file_info(path)
        info.update({"mime_type": "image/png", "frame": hou.frame(),
                     "image_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
        return info
    raise ValueError(f"Unknown command: {command}")


def start(session_file):
    global _service
    if _service is not None and _service.running:
        return _service
    _service = LocalService(dispatch, session_file, {"houdini_version": hou.applicationVersionString(),
                                                    "ui_available": hou.isUIAvailable()})
    _service.start()
    if hou.isUIAvailable():
        hou.ui.addEventLoopCallback(_service.drain_one)
    return _service


def stop():
    global _service
    if _service is None:
        return
    if hou.isUIAvailable():
        hou.ui.removeEventLoopCallback(_service.drain_one)
    _service.stop()
    _service = None


def run_headless(session_file):
    service = start(session_file)
    try:
        while service.running:
            service.drain_one()
            time.sleep(0.01)
    finally:
        stop()
