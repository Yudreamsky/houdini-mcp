"""Run with hython: turn a maze MCP result into an editable, self-contained HIP."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import hou

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hlab.wfc import solve


def build(source, output):
    if hou.isUIAvailable():
        raise RuntimeError("Run this example in a fresh hython process, outside the current GUI session")
    if output.exists():
        raise FileExistsError(f"Choose a new HIP path: {output}")
    if output.suffix.lower() != ".hip":
        raise ValueError("Output must end in .hip")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload["case"] != "maze":
        raise ValueError("This geometry example builds the maze grammar")
    solver = (ROOT / "hlab/wfc.py").read_bytes()
    if hashlib.sha256(solver).hexdigest() != payload["solver_sha256"]:
        raise ValueError("Solver changed; regenerate the layout with examples/wfc/run.py")
    request, expected = payload["request"], payload["result"]
    if solve(**request) != expected:
        raise ValueError("Saved result does not reproduce from its request")
    if hou.node("/obj").children():
        raise RuntimeError("Expected an empty hython scene")

    root = hou.node("/obj").createNode("geo", "WFC_MAZE", run_init_scripts=False)
    root.addSpareParmTuple(hou.IntParmTemplate("seed", "Layout seed", 1, (request["seed"],)))
    for name, label, value in (("pitch", "Cell pitch (m)", 1.6),
                               ("wall_height", "Wall height (m)", 2.05),
                               ("wall_thickness", "Wall thickness (m)", .14)):
        root.addSpareParmTuple(hou.FloatParmTemplate(name, label, 1, (value,), min=.01, min_is_strict=True))
    layout = root.createNode("python", "WFC_LAYOUT")
    driver = f'''
import json, hou
node = hou.pwd()
request = json.loads({json.dumps(request)!r})
request["seed"] = node.parent().evalParm("seed")
result = solve(**request)
geometry = node.geometry()
geometry.addAttrib(hou.attribType.Global, "wfc_result", "")
geometry.setGlobalAttribValue("wfc_result", json.dumps(result))
'''
    layout.parm("python").set(solver.decode("utf-8") + "\n" + driver)
    model = layout.createOutputNode("python", "BUILD_WALLS")
    model.parm("python").set(Path(__file__).with_name("maze_geometry.py").read_text(encoding="utf-8"))
    output_node = model.createOutputNode("null", "OUT_MAZE")
    output_node.setDisplayFlag(True)
    output_node.setRenderFlag(True)
    root.layoutChildren()
    geometry = output_node.geometry()
    if layout.errors() or model.errors():
        raise RuntimeError(str((layout.errors(), model.errors())))
    if json.loads(geometry.stringAttribValue("wfc_result")) != expected:
        raise RuntimeError("Embedded solver differs from the MCP result")

    camera = hou.node("/obj").createNode("cam", "Maze_camera")
    center = (request["columns"] * .8, 0, -request["rows"] * .8)
    position = (center[0] + 20, 30, center[2] + 26)
    dx, dy, dz = [a-b for a, b in zip(position, center)]
    camera.parmTuple("t").set(position)
    camera.parmTuple("r").set((-math.degrees(math.atan2(dy, math.hypot(dx, dz))),
                              math.degrees(math.atan2(dx, dz)), 0))
    camera.setParms(dict(projection="ortho", orthowidth=32., resx=1280, resy=900))
    camera.setDisplayFlag(False)
    hou.node("/obj").layoutChildren()
    root.setCurrent(True, clear_all_selected=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    hou.hipFile.save(str(output), save_to_recent_files=False)
    print(json.dumps(dict(hip=str(output), points=len(geometry.points()), primitives=len(geometry.prims()),
                         wall_segments=geometry.intAttribValue("wall_segments"), seed=request["seed"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    build(options.layout.resolve(), options.output.resolve())
