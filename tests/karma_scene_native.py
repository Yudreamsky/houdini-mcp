"""Run python -m tests.karma_scene_native for real renders with temporary scene edits: a parameter override moves the
ball and replaces its animation, a hidden object is left out, on Karma and (where installed) Chaos Vantage, and the
HIP on disk never changes. Skips when other programs hold the GPU."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from tests.karma_animate_native import ball_top as karma_ball_top
from tests.karma_lighting_native import patch_mean
from tests.vantage_native import ball_top as vantage_ball_top

BOX_FRONT = (.2, .6, .38, .9)  # picture fractions covered by the white box's front face
LIFT = {"/obj/BALL/ty": 1.0}


def accept(directory):
    from PIL import Image
    from hlab import karma, vantage
    from hlab.runtime import discover
    from hlab.storage import sha
    from hlab.worker_pool import pool

    busiest = max((karma.gpu_load() or {}).get("utilization_percent", 0) for _ in range(3))
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    hip = directory / "rising.hip"  # a ball that rises one unit over frames 1-24, a white box, a ground
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
        look = {"engine": engine, "lighting": "day", "max_edge": 640, "samples": 32}
        top = vantage_ball_top if engine == "vantage" else karma_ball_top

        def shot(**edits):
            run, _ = karma.render(str(hip), "/obj/CAM", 1, changes=look, **edits)
            assert run["status"] == "completed" and run["hip_unchanged"], run["notes"]
            with Image.open(run["path"]) as picture:
                rgb = picture.convert("RGB")
            return run, top(rgb.convert("L")), patch_mean(rgb, BOX_FRONT)

        plain, plain_top, plain_box = shot()
        lifted, lifted_top, _ = shot(overrides=LIFT)
        hidden, hidden_top, hidden_box = shot(hide=["/obj/BOX"])
        # One unit up is far more than a frame of the ball's own animation.
        assert plain_top - lifted_top > 30, (engine, plain_top, lifted_top)
        change = lifted["scene"]["overrides"][0]
        assert change == {"parm": "/obj/BALL/ty", "from": 0.0, "to": 1.0, "was_animated": True}, change
        assert "原来有动画" in lifted["notes"][0] and "临时改 1 个场景参数" in lifted["summary"], lifted["notes"]
        # Without the white box its place shows the ground, and the ball has not moved.
        assert hidden_box < plain_box * .75 and abs(hidden_top - plain_top) <= 2, (engine, plain_box, hidden_box)
        assert hidden["scene"]["hidden"] == ["/obj/BOX"] and "隐藏 1 个物体" in hidden["summary"], hidden["scene"]
        assert plain["scene"] == {"overrides": [], "hidden": []}, plain["scene"]
        seen[engine] = {"ball top": [plain_top, lifted_top], "box front": [round(plain_box, 3), round(hidden_box, 3)]}

    # In an animation the override replaces the ball's keyframes: it stays put on every frame.
    clip, _ = karma.animate(str(hip), "/obj/CAM", [1, 4], "preview", {"lighting": "day", "max_edge": 640}, 24,
                            overrides=LIFT)
    tops = []
    for frame in sorted(Path(clip["frames_folder"]).glob("f*.png")):
        with Image.open(frame) as picture:
            tops.append(karma_ball_top(picture.convert("L")))
    assert len(tops) == 4 and max(tops) - min(tops) <= 1, tops

    for edits, message in (({"overrides": {"/obj/BALL/nope": 1}}, "no parameter /obj/BALL/nope"),
                           ({"hide": ["/obj/NOWHERE"]}, "not an object: /obj/NOWHERE"),
                           ({"overrides": {"/obj/BALL/ty": "up"}}, "cannot set /obj/BALL/ty")):
        try:
            karma.render(str(hip), "/obj/CAM", 1, changes={"max_edge": 320}, **edits)
            raise AssertionError(f"accepted {edits}")
        except ValueError as exc:
            assert message in str(exc), exc
    assert sha(hip) == before
    pool.close()
    print("PASS scene edits for one render: override moves the ball and freezes its animation, a hidden box is left out,",
          "bad paths are refused, the HIP is unchanged:", seen, "| animation tops", tops)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="karma-scene-acceptance-") as tmp:
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            accept(Path(tmp))
