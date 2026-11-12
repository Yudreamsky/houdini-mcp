"""Run python -m tests.karma_animate_native for real Karma animations on this machine: a range renders in one husk
run, far quicker per frame than frame-by-frame stills; frames the time limit stops are named and the rest still
render; long ranges render in several runs. Skips when other programs hold the GPU."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch



def ball_top(picture):
    """The first row from the top where the chrome ball shows against the day sky (about 113 of 255) in its columns."""
    w, h = picture.size
    for y in range(int(h * .1), int(h * .9)):
        if min(picture.getpixel((x, y)) for x in range(int(w * .6), int(w * .78), 4)) < 80:
            return y
    return None


def accept(directory):
    from PIL import Image
    from hlab import karma
    from hlab.runtime import discover
    from hlab.storage import sha
    from hlab.worker_pool import pool

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

    # A ball that rises one unit over frames 1-24 (the Vantage fixture).
    hip = directory / "rising.hip"
    subprocess.run([str(discover().hython), "-m", "tests.vantage_native", str(hip)], check=True,
                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL)
    before = sha(hip)
    look = {"lighting": "day", "max_edge": 640, "samples": 32}
    # The first XPU render of a session compiles shaders and prepares the denoiser; time the still after it.
    karma.render(str(hip), "/obj/CAM", 1, changes=look)
    still, _ = timed("one still", karma.render, str(hip), "/obj/CAM", 2, changes=look)

    clip, sheet = timed("12 frames", karma.animate, str(hip), "/obj/CAM", [1, 12], "preview", look, 24)
    folder = Path(clip["folder"])
    frames = sorted(Path(clip["frames_folder"]).glob("f*.png"))
    assert clip["frame_count"] == len(frames) == 12 and clip["status"] == "completed", clip
    assert clip["gpu_verified"] and clip["hip_unchanged"] and sha(hip) == before, clip["notes"]
    assert len(list(folder.glob("husk-F*.log"))) == 1, "the whole range should be one husk run"
    assert clip["limited_frames"] == [] and clip["resumed_at"] == [], clip
    share = sum(d["contribution_percent"] for d in clip["devices"])
    assert 99 <= share <= 101, clip["devices"]  # the last frame's devices, not one set per frame
    assert "显卡贡献 100%" in clip["summary"], clip["summary"]
    # The sun stays where the first frame's camera put it, and the ball rises on every frame.
    tops = []
    for frame in frames:
        with Image.open(frame) as picture:
            assert picture.size == (640, 360)
            tops.append(ball_top(picture.convert("L")))
    assert all(b < a for a, b in zip(tops, tops[1:])), tops
    assert clip["video"] is None or Path(clip["video"]).stat().st_size > 1000
    assert sheet.width == 3 * 426
    # Frame by frame, each frame cost a still: a scene load, a husk start and a shader check.
    assert seconds["12 frames"] < 12 * seconds["one still"] / 2, seconds

    # Frames stopped by the time limit are saved and named; husk's crash on exit does not lose the range.
    slow, _ = timed("3 limited frames", karma.animate, str(hip), "/obj/CAM", [3, 5], "preview",
                    {**look, "samples": 16384, "max_edge": 960, "denoiser": "off", "time_limit": 2}, 24)
    assert slow["frame_count"] == 3 and slow["status"] == "time_limit" and slow["limited_frames"] == [3, 4, 5], slow
    assert "3 帧到了时间上限" in " ".join(slow["notes"]), slow["notes"]

    # A range longer than one run, on the CPU engine: two runs, every frame in order.
    with patch("hlab.karma.CHUNK", 2):
        cpu, _ = timed("3 cpu frames in 2 runs", karma.animate, str(hip), "/obj/CAM", [10, 12], "preview",
                       {"engine": "cpu", "width": 160, "samples": 4, "denoiser": "off"}, 24)
    assert cpu["frame_count"] == 3 and cpu["settings"]["engine"] == "cpu" and cpu["status"] == "completed", cpu
    assert sorted(p.name for p in Path(cpu["folder"]).glob("husk-F*.log")) == ["husk-F10.log", "husk-F12.log"]
    assert sha(hip) == before
    pool.close()
    print("PASS Karma animation: 12 frames in one husk run, ball rising", tops[0], "->", tops[-1],
          "; time-limited frames named; CPU range in 2 runs:", seconds)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="karma-animate-acceptance-") as tmp:
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            accept(Path(tmp))
