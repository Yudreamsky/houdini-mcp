"""Run python -m tests.vantage_native for real Chaos Vantage renders beside Karma on this machine: matching light
levels, the sky behind, rounded edges, PBR fixes and a short animation. Skips when Vantage is not installed or other
programs hold the GPU."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from tests.karma_lighting_native import patch_mean


def fixture(target):
    """Values no real material has, and a ball that rises one unit over frames 1-24."""
    import hou
    hou.hipFile.clear(suppress_save_prompt=True)
    obj, mat = hou.node("/obj"), hou.node("/mat")
    paper = mat.createNode("principledshader::2.0", "paper_white")
    paper.parmTuple("basecolor").set((1, 1, 1))
    paper.parm("reflect").set(0)
    chrome = mat.createNode("mtlxstandard_surface", "dark_chrome")
    chrome.parmTuple("base_color").set((.2, .2, .2))
    chrome.parm("metalness").set(1)
    chrome.parm("specular_roughness").set(0)
    for name, sop, material, parms in (("BOX", "box", paper.path(), {"t": (-.8, .5, 0)}),
                                       ("BALL", "sphere", chrome.path(), {"type": 2, "freq": 12, "t": (.8, .5, 0),
                                                                          "rad": (.5, .5, .5)}),
                                       ("GROUND", "grid", "", {"size": (10, 10)})):
        geo = obj.createNode("geo", name)
        node = geo.createNode(sop)
        for key, value in parms.items():
            (node.parmTuple(key) if isinstance(value, tuple) else node.parm(key)).set(value)
        node.setDisplayFlag(True)
        node.setRenderFlag(True)
        geo.parm("shop_materialpath").set(material)
    for frame, height in ((1, 0.), (24, 1.)):
        key = hou.Keyframe()
        key.setFrame(frame)
        key.setValue(height)
        hou.node("/obj/BALL").parm("ty").setKeyframe(key)
    cam = obj.createNode("cam", "CAM")
    cam.parmTuple("t").set((0, 1.6, 5))
    cam.parmTuple("r").set((-10, 0, 0))
    cam.parm("resx").set(1280)
    cam.parm("resy").set(720)
    hou.playbar.setFrameRange(1, 24)
    hou.setFrame(1)
    hou.hipFile.save(str(target), save_to_recent_files=False)


def ball_top(picture):
    """The first row from the top where the dark ball shows in its columns."""
    w, h = picture.size
    for y in range(int(h * .1), int(h * .9)):
        if min(picture.getpixel((x, y)) for x in range(int(w * .6), int(w * .78), 4)) < 30:
            return y
    return None


def no_dark_seam(picture, x):
    """Across the horizon no pixel is darker than both the sky above and the ground below it."""
    column = [sum(picture.getpixel((x, y))[:3]) / 3 for y in range(picture.height)]
    for y in range(2, picture.height - 2):
        if column[y] < min(column[y - 2], column[y + 2]) - 6:
            return False
    return True


def accept(directory):
    from PIL import Image
    from hlab import karma, vantage
    from hlab.runtime import discover
    from hlab.storage import sha
    from hlab.worker_pool import pool

    try:
        vantage.executable()
    except ValueError as exc:
        print("SKIP", exc)
        return
    loads = []
    for _ in range(5):
        loads.append(karma.gpu_load() or {})
        time.sleep(.4)
    busiest = max(load.get("utilization_percent", 0) for load in loads)
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    seconds = {}

    def timed(label, call, *args, **kwargs):
        start = time.perf_counter()
        value = call(*args, **kwargs)
        seconds[label] = round(time.perf_counter() - start, 2)
        return value

    sample = karma.scene("karma-probe")
    before = sha(sample)
    base = {"lighting": "day", "max_edge": 640, "samples": 64, "denoiser": "off"}
    # XPU, like Vantage, renders the red Principled box through an approximation; CPU runs the shader itself.
    reference, _ = timed("karma xpu", karma.render, "karma-probe", changes={**base, "engine": "xpu"})
    still, _ = timed("vantage still", karma.render, "karma-probe", changes={**base, "engine": "vantage"})
    assert still["status"] == "completed" and still["gpu_verified"] and still["hip_unchanged"], still["notes"]
    assert still["settings"]["engine"] == "vantage" and still["resolution"] == reference["resolution"] == [640, 360]
    assert still["render_seconds"] < 10 and still["startup_seconds"] > 0 and still["export_seconds"] < 60, still
    notes = " ".join(still["notes"])
    for text in ("平滑法线", "折算成常数", "和 Karma 一样的灰", "按灯的类型调暗"):
        assert text in notes, (text, still["notes"])
    # Same light, same materials: within 15% of Karma on lit ground, shade, both objects and the box's foot, where a
    # node-computed colour used to bounce white.
    with Image.open(reference["path"]) as k, Image.open(still["path"]) as v:
        karma_picture, vantage_picture = k.convert("RGB"), v.convert("RGB")
    patches = {"open ground": (.85, .86, .98, .97), "box shadow": (.1, .72, .15, .8), "box front": (.2, .5, .38, .75),
               "ball": (.72, .45, .78, .5), "box foot": (.22, .87, .38, .9)}
    ratios = {name: patch_mean(vantage_picture, box) / patch_mean(karma_picture, box) for name, box in patches.items()}
    assert all(.85 < r < 1.15 for r in ratios.values()), ratios
    # The sky is composited behind: opaque, blue above and without a dark seam at the horizon.
    sky = vantage_picture.crop((0, 0, 640, 8)).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    r, g, b = sky
    assert b > r + 10, (r, g, b)
    assert no_dark_seam(vantage_picture, 20) and no_dark_seam(vantage_picture, 620), "dark line along the horizon"

    hip = directory / "unreal.hip"
    subprocess.run([str(discover().hython), str(Path(__file__).resolve()), str(hip)], check=True, timeout=180)
    unreal = sha(hip)
    report = {row["material"]: sorted(i["code"] for i in row["issues"]) for row in karma.inspect(str(hip))["pbr"]}
    assert report == {"/mat/dark_chrome": ["dark_metal", "mirror_smooth"],
                      "/mat/paper_white": ["no_reflection", "too_bright"]}, report
    photoreal = {"pbr_fix": True, "round_edges": 20, "lighting": "studio", "max_edge": 480}
    for engine in ("xpu", "cpu", "vantage"):
        run, _ = timed(f"photoreal {engine}", karma.render, str(hip), changes={**photoreal, "engine": engine})
        # The fixes land on the authored materials before any conversion, so converted copies keep them.
        fixes = {row["material"]: row["changes"] for row in run["photoreal"]["pbr_fixes"]}
        assert set(fixes) == {"/mat/dark_chrome", "/mat/paper_white"}, run["photoreal"]
        assert len(fixes["/mat/paper_white"]) == 2 and len(fixes["/mat/dark_chrome"]) == 2, fixes
        rounded = run["photoreal"]["round_edges"]
        assert rounded and (rounded.get("materials") or rounded.get("objects")), rounded
        assert run["settings"]["round_edges"] == 20 and run["settings"]["pbr_fix"] is True
        assert "圆角" in run["summary"] and "改正" in run["summary"], run["summary"]
        assert ("真实倒角" if engine == "vantage" else "圆角（着色时混合法线") in " ".join(run["notes"]), run["notes"]

    clip, sheet = timed("vantage animation", karma.animate, str(hip), "/obj/CAM", [1, 12], "preview",
                        {"engine": "vantage", "lighting": "day"}, 24)
    assert clip["frame_count"] == clip["frames_rendered"] == 12 and clip["status"] == "completed", clip
    assert clip["export_seconds"] < 60, "the export should write only the requested frames"
    assert clip["video"] is None or Path(clip["video"]).stat().st_size > 1000
    # The ball rises on every frame through the last: a lost object transform used to freeze the end of the clip.
    tops = []
    for frame in sorted(Path(clip["frames_folder"]).glob("f*.png")):
        with Image.open(frame) as picture:
            tops.append(ball_top(picture.convert("L")))
    assert all(b < a for a, b in zip(tops, tops[1:])), tops
    assert sheet.width == 3 * 426
    assert sha(sample) == before and sha(hip) == unreal
    pool.close()
    print("PASS Vantage beside Karma (light levels within 15%:", {k: round(v, 3) for k, v in ratios.items()},
          "), sky behind, PBR report and fixes, rounded edges on XPU/CPU/Vantage, 12-frame animation:", seconds)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fixture(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="vantage-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
                accept(Path(tmp))
