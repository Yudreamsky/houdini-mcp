"""Run python -m tests.karma_tone_native for real Karma renders developed from linear EXR: AgX keeps the shape of an
overexposed scene where the plain picture clips to white, exposure brightens the result, exr keeps the linear original,
and an animation develops every frame. Skips when other programs hold the GPU."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.karma_lighting_native import patch_mean

BRIGHT = {"lighting": "day", "light_exposure": 2.5, "max_edge": 640, "samples": 32}  # deliberately overexposed


def clipped(picture):
    """The share of pixels that are white in every channel."""
    data = picture.convert("RGB").tobytes()
    return sum(1 for i in range(0, len(data), 3) if min(data[i:i + 3]) >= 250) / (len(data) // 3)


def accept():
    from PIL import Image
    from hlab import karma
    from hlab.storage import sha
    from hlab.worker_pool import pool

    busiest = max((karma.gpu_load() or {}).get("utilization_percent", 0) for _ in range(3))
    if busiest >= 70:
        print(f"SKIP the GPU is {busiest:g}% busy with other programs; rerun when it is idle")
        return
    sample = karma.scene("karma-probe")
    before = sha(sample)
    seen = {}

    def shot(**changes):
        run, _ = karma.render("karma-probe", changes={**BRIGHT, **changes})
        assert run["status"] == "completed" and run["hip_unchanged"], run["notes"]
        with Image.open(run["path"]) as picture:
            rgb = picture.convert("RGB")
        return run, clipped(rgb), patch_mean(rgb, (0., 0., 1., 1.))

    plain, plain_white, plain_mean = shot()
    film, film_white, film_mean = shot(tone="agx")
    punchy, _, _ = shot(tone="agx_punchy")
    darker, _, darker_mean = shot(tone="agx", exposure=-2)
    kept, kept_white, kept_mean = shot(exr=True)
    # The overexposed day clips a large part of the plain picture; AgX rolls it off.
    assert plain_white > .15 and film_white < plain_white * .2, (plain_white, film_white)
    assert darker_mean < film_mean * .7, (film_mean, darker_mean)
    assert film["settings"]["tone"] == "agx" and "色调 AgX" in film["summary"] and "exr" not in film, film["summary"]
    assert "（加强）" in punchy["summary"] and "成片曝光 -2 档" in darker["summary"], (punchy["summary"], darker["summary"])
    # exr alone keeps the linear original and shows the same picture as Karma's own PNG.
    original = Path(kept["exr"])
    assert original.is_file() and original.read_bytes()[:4] == bytes((0x76, 0x2f, 0x31, 0x01)), kept["exr"]
    assert abs(kept_mean - plain_mean) < plain_mean * .04 and abs(kept_white - plain_white) < .03, (plain_mean, kept_mean)
    assert plain["settings"]["tone"] == "off" and plain["settings"]["exr"] is False and "色调" not in plain["summary"]
    seen["white share"] = {"plain": round(plain_white, 3), "agx": round(film_white, 3), "exr only": round(kept_white, 3)}
    seen["mean"] = {"plain": round(plain_mean, 3), "agx": round(film_mean, 3), "agx -2 stops": round(darker_mean, 3)}

    clip, _ = karma.animate("karma-probe", "", [1, 3], "preview", {**BRIGHT, "tone": "agx", "exr": True}, 24)
    frames = sorted(Path(clip["frames_folder"]).glob("f*.png"))
    originals = sorted(Path(clip["exr_folder"]).glob("f*.exr"))
    assert len(frames) == len(originals) == 3 and clip["status"] == "completed", clip
    with Image.open(frames[-1]) as picture:
        assert clipped(picture) < plain_white * .2
    for changes, message in (({"engine": "vantage", "tone": "agx"}, "only apply to Karma"),):
        try:
            karma.render("karma-probe", changes=changes)
            raise AssertionError(f"accepted {changes}")
        except ValueError as exc:
            assert message in str(exc), exc
    assert sha(sample) == before
    pool.close()
    print("PASS developed renders: AgX keeps overexposed highlights, exposure darkens, exr keeps the linear original,",
          "an animation develops each frame:", seen)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="karma-tone-acceptance-") as tmp:
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            accept()
