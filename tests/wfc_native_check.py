"""Hython worker: reopen the generated HIP and check passages against its actual mesh."""

import json
from pathlib import Path
import sys

import hou

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.wfc.rules import COLS, ROWS, STEPS, maze_metrics


def check(hip, report):
    hou.hipFile.load(str(hip), suppress_save_prompt=True)
    root = hou.node("/obj/WFC_MAZE")
    output = root.node("OUT_MAZE")
    cases = []
    for seed, pitch, height in ((4, 1.6, 2.05), (25, 1.6, 2.05), (7, 1.8, 1.5)):
        root.setParms(dict(seed=seed, pitch=pitch, wall_height=height))
        geometry = output.geometry()
        assert not output.errors() and not root.node("BUILD_WALLS").errors()
        result = json.loads(geometry.stringAttribValue("wfc_result"))
        metrics = maze_metrics(result["layout"])
        assert metrics["reachable"] == 143 and metrics["interior_edges"] == 142
        rays = 0
        for y in range(ROWS):
            for x in range(COLS):
                for side, _, dx, dy in STEPS:
                    for h in (.2 * height, .8 * height):
                        for offset in (-.3 * pitch, 0, .3 * pitch):
                            origin = hou.Vector3((x+.5)*pitch + dy*offset, h, -(y+.5)*pitch + dx*offset)
                            direction = hou.Vector3(dx, 0, -dy)
                            hit = geometry.intersect(origin, direction, hou.Vector3(), hou.Vector3(), hou.Vector3(),
                                                     min_hit=.001, max_hit=pitch)
                            assert (hit < 0) == (side in result["layout"][y][x]), (seed, x, y, side, h, offset)
                            rays += 1
        assert abs(geometry.boundingBox().maxvec()[1] - height) < 1e-5
        cases.append(dict(seed=seed, pitch_m=pitch, wall_height_m=height, rays=rays,
                          reachable=metrics["reachable"], interior_edges=metrics["interior_edges"],
                          steps=metrics["steps"], stats=result["stats"], primitives=len(geometry.prims())))
    with report.open("x", encoding="utf-8") as stream:
        json.dump(dict(houdini=hou.applicationVersionString(), hip=str(hip), cases=cases), stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(report=str(report), cases=len(cases), rays=sum(c["rays"] for c in cases))))


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
