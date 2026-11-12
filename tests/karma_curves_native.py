"""Run python -m tests.karma_curves_native for real renders of thick side-lit curves: on Karma CPU flat ribbons catch
more light than rounded tubes, and XPU, which renders every style alike, refuses the setting instead of ignoring it."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def fixture(folder):
    """Nine upright curves a fifth of a unit wide, lit from the side."""
    import hou
    hou.hipFile.clear(suppress_save_prompt=True)
    obj = hou.node("/obj")
    geo = obj.createNode("geo", "HAIRS")
    lines = geo.createNode("attribwrangle")
    lines.parm("class").set(0)
    lines.parm("snippet").set("for (int i = 0; i < 9; i++) addprim(0, 'polyline', addpoint(0, set(-2 + i * 0.5, -1, 0)), "
                              "addpoint(0, set(-2 + i * 0.5, 1, 0)));")
    width = lines.createOutputNode("attribwrangle")
    width.parm("snippet").set("f@width = 0.2;")
    width.setDisplayFlag(True)
    width.setRenderFlag(True)
    light = obj.createNode("hlight::2.0", "SIDE")
    light.parm("light_type").set("distant")
    light.parmTuple("r").set((0, 70, 0))
    light.parm("light_intensity").set(3)
    cam = obj.createNode("cam", "CAM")
    cam.parmTuple("t").set((0, 0, 8))
    cam.setParms({"resx": 480, "resy": 270})
    hou.hipFile.save(str(folder / "curves.hip"), save_to_recent_files=False)


def lit(picture):
    """How many pixels the curves cover and their mean brightness."""
    data = picture.convert("L").tobytes()
    bright = [v for v in data if v > 10]
    return len(bright), sum(bright) / len(bright)


def accept(directory):
    from PIL import Image
    from hlab import karma
    from hlab.runtime import discover
    from hlab.worker_pool import pool

    subprocess.run([str(discover().hython), "-m", "tests.karma_curves_native", str(directory)], check=True,
                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL)
    hip = str(directory / "curves.hip")
    seen = {}
    for style in ("rounded", "ribbons"):
        run, _ = karma.render(hip, changes={"engine": "cpu", "samples": 32, "denoiser": "off", "width": 480, "curves": style})
        assert run["status"] == "completed" and run["settings"]["curves"] == style, run["settings"]
        assert ("曲线按扁带" in run["summary"]) == (style == "ribbons"), run["summary"]
        with Image.open(run["path"]) as picture:
            seen[style] = lit(picture)
    # A ribbon faces the camera across its whole width; a tube's sides turn away from the light.
    assert seen["ribbons"][0] > seen["rounded"][0] * 1.03 and seen["ribbons"][1] > seen["rounded"][1] * 1.08, seen
    for changes in ({"curves": "ribbons"}, {"engine": "xpu", "curves": "ribbons"}):
        try:
            karma.render(hip, changes=changes)
            raise AssertionError(f"accepted {changes}")
        except ValueError as exc:
            assert "only shows with engine = cpu" in str(exc), exc
    plain, _ = karma.render(hip, changes={"samples": 16, "width": 480})  # XPU without the setting is unchanged
    assert plain["settings"]["curves"] == "rounded", plain["settings"]
    pool.close()
    print("PASS curve style: on CPU ribbons cover and shine more than tubes", seen, "; XPU refuses ribbons")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fixture(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="karma-curves-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
                accept(Path(tmp))
