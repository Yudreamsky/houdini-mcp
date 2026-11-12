"""Run python -m tests.karma_lighting_native for real Karma renders of every lighting look on the Karma sample."""
import os
import statistics
import tempfile
import time
from unittest.mock import patch


def linear(c):
    c /= 255
    return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4


def patch_mean(picture, box):
    """Mean linear luminance of a pixel box given as fractions of the image."""
    w, h = picture.size
    data = picture.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))).convert("RGB").tobytes()
    return statistics.fmean(.2126 * linear(data[i]) + .7152 * linear(data[i + 1]) + .0722 * linear(data[i + 2])
                            for i in range(0, len(data), 3))


def accept():
    from PIL import Image, ImageStat
    from hlab import karma
    from hlab.storage import sha
    from hlab.worker_pool import pool

    seconds = {}
    sample = karma.scene("karma-probe")
    before = sha(sample)
    # CPU renders give the same light levels as XPU and do not depend on what else holds the GPU.
    base = {"engine": "cpu", "samples": 32, "denoiser": "off", "max_edge": 320}

    def shot(label, **changes):
        start = time.perf_counter()
        run, _ = karma.render("karma-probe", changes={**base, **changes})
        seconds[label] = round(time.perf_counter() - start, 2)
        assert run["status"] == "completed" and run["hip_unchanged"], run["notes"]
        with Image.open(run["path"]) as picture:
            return run, picture.convert("RGBA")

    day, sunny = shot("day", lighting="day")
    lit = day["lighting"]
    assert lit["added"] == ["/obj/HR_KARMA_SUN", "/obj/HR_KARMA_SKY"] and lit["turned_off"] == ["/obj/KEY"], lit
    assert (day["settings"]["lighting"], day["settings"]["light_angle"], day["settings"]["light_elevation"]) == ("day", 30, 35)
    assert day["lights"] == 2 and "日景" in day["notes"][0]
    # The sky is the background: opaque and blue above the horizon.
    top = sunny.crop((0, 0, sunny.width, 8))
    assert top.getchannel("A").getextrema()[0] == 255
    r, g, b, _ = ImageStat.Stat(top).mean
    assert b > r + 10, (r, g, b)
    # The green ball sits right of centre; a sun from the picture's right lights its right half and vice versa.
    left, right = (.6, .52, .66, .62), (.72, .52, .78, .62)
    _, from_right = shot("day from the right", lighting="day", light_angle=90)
    _, from_left = shot("day from the left", lighting="day", light_angle=-90)
    assert patch_mean(from_right, right) > 2 * patch_mean(from_right, left), "a sun from the right should light the right"
    assert patch_mean(from_left, left) > 2 * patch_mean(from_left, right), "a sun from the left should light the left"
    overcast, grey = shot("overcast", lighting="overcast")
    assert overcast["lighting"]["added"] == ["/obj/HR_KARMA_SKY"] and "light_fill" not in overcast["settings"]
    # Open ground against the ground in the box's shadow: a clear day has hard contrast, an overcast sky almost none.
    open_ground, shade = (.4, .9, .55, .98), (.12, .68, .15, .75)
    contrast = [patch_mean(p, open_ground) / patch_mean(p, shade) for p in (sunny, grey)]
    assert contrast[0] > 3 and contrast[1] < 1.5, contrast
    # Less fill darkens the sky-lit shadow and leaves the sunlit ground nearly as it was.
    harder, punchy = shot("day, fill -1 stop", lighting="day", light_fill=-1)
    assert harder["settings"]["light_fill"] == -1
    assert patch_mean(punchy, shade) < .7 * patch_mean(sunny, shade), "less fill should darken the shadow"
    assert patch_mean(punchy, open_ground) > .8 * patch_mean(sunny, open_ground)
    # One stop doubles the light where nothing clips.
    _, brighter = shot("overcast +1 stop", lighting="overcast", light_exposure=1)
    ground = (.05, .85, .3, .98)
    ratio = patch_mean(brighter, ground) / patch_mean(grey, ground)
    assert 1.7 < ratio < 2.3, ratio
    night, dark = shot("night", lighting="night")
    assert night["lighting"]["kept"] == ["/obj/KEY"] and night["lighting"]["turned_off"] == []
    assert night["settings"]["keep_scene_lights"] is True
    _, moonlit = shot("night without scene lights", lighting="night", keep_scene_lights=False)
    whole = (0, 0, 1, 1)
    assert patch_mean(moonlit, whole) < patch_mean(dark, whole) < patch_mean(sunny, whole)
    assert patch_mean(moonlit, whole) < .4 * patch_mean(sunny, whole)
    studio, product = shot("studio", lighting="studio")
    names = [p.rsplit("/", 1)[1] for p in studio["lighting"]["added"]]
    assert names == ["HR_KARMA_KEY", "HR_KARMA_FILL", "HR_KARMA_RIM", "HR_KARMA_SKY"], names
    assert studio["lighting"]["subject"]["radius"] > 1
    # A neutral grey backdrop, brightest behind the subject and darker toward the picture's corners.
    rgb = product.convert("RGB")
    corner, middle = rgb.getpixel((3, 3)), rgb.getpixel((rgb.width // 2, 3))
    assert max(corner) - min(corner) <= 3 and linear(middle[0]) > 1.5 * linear(corner[0]) > .02, (corner, middle)
    assert sha(sample) == before
    pool.close()
    print("PASS lighting looks: lights added and turned off, camera-relative direction, exposure, fill, overcast "
          "softness, night levels and kept lights, studio rig and backdrop:", seconds)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="karma-lighting-") as tmp:
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
            accept()
