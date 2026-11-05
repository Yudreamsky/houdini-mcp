"""Run python -m tests.karma_native for real Karma XPU/CPU renders of saved HIPs that stay unchanged."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def fixture(sample, copy):
    import hou
    hou.hipFile.load(str(sample), suppress_save_prompt=True)
    rop = hou.node("/out").createNode("karma", "LOOKDEV")
    rop.parm("camera").set("/obj/CAM")
    rop.parm("engine").set("cpu")
    rop.parm("convergence_mode").set("Path Traced")
    rop.parm("pathtracedsamples").set(6)
    side = hou.node("/obj").createNode("cam", "SIDE")
    side.parmTuple("t").set((5, 1.5, 0))
    side.parmTuple("r").set((-10, 90, 0))
    side.parm("resx").set(640)
    side.parm("resy").set(640)
    # A legacy constant shader on a backdrop: Karma ignores /shop, so only a conversion shows the flat Cd colour.
    backdrop = hou.node("/obj").createNode("geo", "BACKDROP")
    grid = backdrop.createNode("grid")
    grid.parmTuple("size").set((16, 10))
    grid.parm("orient").set(0)
    grid.parmTuple("t").set((0, 3, -4.5))
    paint = backdrop.createNode("attribwrangle")
    paint.setInput(0, grid)
    paint.parm("snippet").set("@Cd = set(0.1, 0.4, 0.9);")
    paint.setDisplayFlag(True)
    paint.setRenderFlag(True)
    hou.node("/shop").createNode("v_constant", "flat")
    backdrop.parm("shop_materialpath").set("/shop/flat")
    hou.hipFile.save(str(copy), save_to_recent_files=False)


def refused(call, text):
    try:
        call()
    except ValueError as exc:
        assert text in str(exc), exc
    else:
        raise AssertionError(f"Expected a refusal mentioning {text!r}")


def accept(directory):
    from PIL import Image
    from hlab import karma
    from hlab.runtime import discover
    from hlab.server import evidence
    from hlab.storage import sha
    from hlab.worker_pool import pool

    seconds = {}

    def timed(label, call, *args, **kwargs):
        start = time.perf_counter()
        value = call(*args, **kwargs)
        seconds[label] = round(time.perf_counter() - start, 2)
        return value

    sample = timed("build sample", karma.scene, "karma-probe")
    scene = timed("inspect", karma.inspect, "karma-probe")
    assert [c["path"] for c in scene["cameras"]] == ["/obj/CAM"] and len(scene["lights"]) == 1
    assert scene["materials"]["counts"] == {"materialx": 1, "principled": 1}
    before = sha(sample)
    run, image = timed("preview xpu", karma.render, "karma-probe", topic="karma-native")
    assert run["status"] == "completed" and run["resolution"] == [960, 540] and run["gpu_verified"]
    assert run["hip_unchanged"] and sha(sample) == before and run["temporary_rop"]
    with Image.open(run["path"]) as picture:
        assert picture.size == (960, 540) and picture.getchannel("A").getextrema()[1] == 255
        assert max(hi - lo for lo, hi in picture.convert("RGB").getextrema()) > 60
    assert [c.type for c in evidence(run["record"])] == ["text", "image"]
    cpu, _ = timed("preview cpu", karma.render, "karma-probe",
                   changes={"engine": "cpu", "denoiser": "oidn", "max_edge": 480})
    assert cpu["settings"]["engine"] == "cpu" and cpu["resolution"] == [480, 270] and not cpu["devices"]
    limited, _ = timed("time limit", karma.render, "karma-probe",
                       changes={"samples": 16384, "time_limit": 2, "denoiser": "off", "max_edge": 640})
    assert limited["status"] == "time_limit" and Path(limited["path"]).is_file() and limited["seconds"] < 60
    copy = directory / "with_rop.hip"
    subprocess.run([str(discover().hython), str(Path(__file__).resolve()), str(sample), str(copy)],
                   check=True, timeout=180)
    copied = sha(copy)
    refused(lambda: karma.render(str(copy)), "/obj/SIDE")
    refused(lambda: karma.render(str(copy), rop="/obj/CAM"), "Karma ROP")
    own, _ = timed("scene rop", karma.render, str(copy), preset="scene", rop="/out/LOOKDEV")
    assert own["camera"] == "/obj/CAM" and not own["temporary_rop"] and own["status"] == "completed"
    assert own["settings"]["engine"] == "cpu" and own["settings"]["samples"] == 6 and sha(copy) == copied
    side, _ = timed("side camera", karma.render, str(copy), camera="/obj/SIDE", changes={"max_edge": 320})
    assert side["resolution"] == [320, 320] and side["gpu_verified"]
    plan = karma.inspect(str(copy))["material_conversion"]
    assert [r["source"] for r in plan["xpu"]["converted"]] == ["/shop/flat"] == [r["source"] for r in plan["cpu"]["converted"]]
    corner = {}
    for engine in ("xpu", "cpu"):
        for convert in (True, False):
            shot, _ = timed(f"backdrop {engine} {'converted' if convert else 'as authored'}", karma.render, str(copy),
                            camera="/obj/CAM", changes={"engine": engine, "max_edge": 320, "convert_materials": convert})
            assert bool(shot["materials"]) == convert and shot["settings"]["convert_materials"] == convert
            assert not convert or [r["source"] for r in shot["materials"]["converted"]] == ["/shop/flat"]
            with Image.open(shot["path"]) as picture:
                corner[engine, convert] = picture.convert("RGB").getpixel((6, 6))
    # Linear Cd (0.1, 0.4, 0.9) written through the sRGB transfer is about (89, 170, 244).
    for engine in ("xpu", "cpu"):
        assert all(abs(a - b) <= 6 for a, b in zip(corner[engine, True], (89, 170, 244))), corner
        assert max(abs(a - b) for a, b in zip(corner[engine, False], (89, 170, 244))) > 30, corner
    assert sha(copy) == copied
    karma.save_preset("细节", "preview", {"samples": 96, "max_edge": 640})
    data, sheet = timed("compare", karma.compare, "karma-probe",
                        {"8": {"samples": 8, "denoiser": "off"}, "细节": {"preset": "细节"}}, zoom=[.5, .35, .85, .85])
    assert data["hip_unchanged"] and sheet.width == 1280 and Path(data["sheet"]).is_file()
    assert [v["resolution"] for v in data["variants"].values()] == [[960, 540], [640, 360]]
    assert all(v["status"] == "completed" and v["gpu_verified"] for v in data["variants"].values())
    assert [c.type for c in evidence(data["id"], variant="细节")] == ["text", "image"]
    pool.close()
    print("PASS Karma sample, inspect, XPU/CPU, time limit, own ROP, camera choice, legacy material conversion, "
          "compare and evidence:", seconds)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        fixture(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        with tempfile.TemporaryDirectory(prefix="karma-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
                accept(Path(tmp))
