"""Run python -m tests.karma_evidence_native: node_lab takes its optical evidence from a HIP's own Karma ROP as it
does from a Mantra ROP. A sweep and a comparison render through Karma, equal variants give pixel-identical pictures,
a single frame renders, and another kind of ROP is refused. Skips when other programs hold the GPU."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROP, BALL = "/out/EVIDENCE", "/obj/BALL/sphere1"


def fixture(folder):
    """The Karma sample with its own small Karma ROP and a geometry ROP that is no renderer."""
    import hou
    from hlab.karma_render import build_sample
    hip = folder / "evidence.hip"
    build_sample(hip)
    rop = hou.node("/out").createNode("karma", "EVIDENCE")
    rop.setParms({"camera": "/obj/CAM", "override_camerares": 0, "resolutionx": 480, "resolutiony": 270,
                  "pathtracedsamples": 16, "convergence_mode": "Path Traced", "engine": "xpu", "denoiser": "off"})
    hou.node("/out").createNode("geometry", "CACHE")
    hou.hipFile.save(str(hip), save_to_recent_files=False)


def accept(directory):
    from hlab import karma
    from hlab.runtime import discover
    from hlab.server import evidence, node_lab
    from hlab.storage import details, sha
    from hlab.worker_pool import pool

    busiest = max((karma.gpu_load() or {}).get("utilization_percent", 0) for _ in range(3))
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    subprocess.run([str(discover().hython), "-m", "tests.karma_evidence_native", str(directory)], check=True,
                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL)
    hip = str(directory / "evidence.hip")
    before = sha(Path(hip))

    def lab(action, **args):
        return json.loads(node_lab(action=action, hip=hip, **args)[0].text)

    sweep = lab("sweep", node=BALL, control="ty", values=[.5, 1.5], frame=1, renderer=ROP, topic="render",
                prediction="the ball rises, so the picture changes", expect_change=True)
    shots = details(sweep["id"])["details"]["samples"]
    assert sweep["observed_change"] and "gap" not in sweep, sweep
    assert all(s["renderer"] == ROP and s["image_id"] for s in shots) and shots[0]["pixel_sha256"] != shots[1]["pixel_sha256"]
    picture = evidence(key=sweep["id"], index=1)[1]
    assert picture.type == "image" and len(picture.data) > 1000

    moved = lab("compare", node=BALL, variants={"low": {"ty": .5}, "high": {"ty": 1.5}}, frame=1, renderer=ROP,
                camera="/obj/CAM", topic="render")
    assert moved["observed_pixel_change"] is True and moved["observed_geometry_change"] is True, moved
    # Karma renders an unchanged scene to the same pixels, so equal variants are reported as no change.
    same = lab("compare", node=BALL, variants={"one": {"ty": .5}, "other": {"ty": .5}}, frame=1, renderer=ROP,
               camera="/obj/CAM", topic="render")
    assert same["observed_pixel_change"] is False and same["observed_geometry_change"] is False, same

    frame = node_lab(action="frame", hip=hip, frame=1, renderer=ROP)
    assert json.loads(frame[0].text)["renderer"] == ROP and frame[1].type == "image"
    try:
        lab("sweep", node=BALL, control="ty", values=[.5, 1.5], frame=1, renderer="/out/CACHE", topic="render")
        raise AssertionError("a geometry ROP was accepted as a renderer")
    except ValueError as exc:
        assert "Mantra or Karma ROP" in str(exc), exc
    assert sha(Path(hip)) == before
    pool.close()
    print("PASS node_lab optical evidence through a Karma ROP: sweep, comparison, identical pictures for equal variants,",
          "single frame, other ROPs refused")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fixture(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="karma-evidence-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
                accept(Path(tmp))
