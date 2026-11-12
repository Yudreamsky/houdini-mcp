"""Run python -m tests.karma_hdri_native for real renders lit by an HDRI panorama: the photograph's sun is found and
turned to the requested side of the camera, it shows behind the scene on Karma and (where installed) Chaos Vantage,
and the HIP never changes. Skips when other programs hold the GPU."""
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.karma_lighting_native import patch_mean

SUN_ELEVATION = 8.  # degrees above the horizon in the generated panorama
LEVEL = {"/obj/CAM/rx": 0}  # the fixture's camera looks 10 degrees down; level, its 26 degree view holds the sun
GROUND = (.05, .8, .3, .95)


def panorama(path):
    """A dim blue sky over brown ground with one small, very bright sun, a fifth of the way along the picture."""
    from hlab.karma_sky import write_hdr
    width, height = 512, 256
    sun_row, sun_col = round((.5 - SUN_ELEVATION / 180.) * height), round(.2 * width)
    rows = []
    for j in range(height):
        base = (.1, .15, .3) if j < height // 2 else (.08, .06, .04)
        rows.append([(300., 280., 240.) if abs(j - sun_row) <= 2 and abs(i - sun_col) <= 2 else base for i in range(width)])
    write_hdr(path, rows)


def sun_column(picture):
    """Where along the picture's width (0-1) its brightest sky pixels are, and how bright."""
    grey = picture.convert("L")
    w, h = grey.size
    sky = grey.crop((0, 0, w, int(h * .4)))
    peak = sky.getextrema()[1]
    columns = [x for x in range(w) if any(sky.getpixel((x, y)) >= peak - 2 for y in range(sky.height))]
    return sum(columns) / len(columns) / w, peak


def accept(directory):
    from PIL import Image
    from hlab import karma, vantage
    from hlab.runtime import discover
    from hlab.storage import sha

    busiest = max((karma.gpu_load() or {}).get("utilization_percent", 0) for _ in range(3))
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    photo = directory / "panorama.hdr"
    panorama(photo)
    hip = directory / "rising.hip"
    subprocess.run([str(discover().hython), "-m", "tests.vantage_native", str(hip)], check=True,
                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL)
    before = sha(hip)
    engines = ["xpu"]
    try:
        vantage.executable()
        engines.append("vantage")
    except ValueError:
        pass
    seen = {}
    for engine in engines:
        row = {}
        for angle in (180, 165):
            run, _ = karma.render(str(hip), "/obj/CAM", 1, changes={"engine": engine, "lighting": "hdri", "hdri": str(photo),
                                                                    "light_angle": angle, "max_edge": 640, "samples": 32},
                                  overrides=LEVEL)
            assert run["status"] == "completed" and run["hip_unchanged"], run["notes"]
            with Image.open(run["path"]) as picture:
                rgb = picture.convert("RGB")
            row[angle] = (*sun_column(rgb), patch_mean(rgb, GROUND))
            lit = run["lighting"]
            assert abs(lit["sun"]["elevation"] - SUN_ELEVATION) < 1.5 and lit["hdri"] == str(photo), lit
            assert run["settings"]["lighting"] == "hdri" and "light_elevation" not in run["settings"], run["settings"]
            assert "环境照片" in " ".join(run["notes"]) and "HDRI 环境" in run["summary"], run["notes"]
        # Straight behind the subject the sun is in the middle of the picture; 15 degrees toward camera-right it is a
        # third of the 45 degree view to the right. It is the background, and it lights the ground.
        centre, right = row[180], row[165]
        assert abs(centre[0] - .5) < .06 and centre[1] > 240, (engine, centre)
        assert .72 < right[0] < .95 and right[1] > 240, (engine, right)
        assert centre[2] > .01 and right[2] > .01, (engine, row)
        seen[engine] = {"sun at 180": round(centre[0], 3), "sun at 165": round(right[0], 3), "ground": round(centre[2], 3)}
    assert sha(hip) == before
    from hlab.worker_pool import pool
    pool.close()
    print("PASS HDRI lighting: the panorama's sun is found, turned to the asked side of the camera and shown behind the scene:", seen)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="karma-hdri-acceptance-") as tmp:
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            accept(Path(tmp))
