import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hlab import karma, karma_sky
from hlab.karma_spec import excerpt, frames_saved, lighting, read_log, read_sequence_log, resolution, settings

LOG = """[08:48:51] >>> Render C:\\job\\render.png (1 of 1) - 640x360 C:/job/usd/__render__.usd frame: 1
[08:48:52] KarmaXPU: Device 0  Status: active  Info: NVidia GPU CUDA/Optix device
[08:48:53] Warning: Unable to find texture brick.rat

Device 0
Type              : Optix
Name              : NVIDIA GeForce RTX 4090
Contrib           : 64%

Device 1
Type              : EmbreeCPU
Name              : Embree CPU device
Contrib           : 35%

[08:48:54] Total Wall Clock Time: 0:01:01.93
[08:48:54]     Peak Memory Usage: 2.14 GiB
[08:48:54] Saved Image: C:\\job\\render.png
"""
LIMIT = """[08:52:49] Run time 2 exceeded file C:\\job\\render.png
307284: Fatal error: Segmentation fault
-- TRACEBACK BEGIN --
+0x7ffe9eaf9c5c [RtlUserThreadStart] C:\\WINDOWS\\SYSTEM32\\ntdll.dll
"""


class SettingsTests(unittest.TestCase):
    def test_presets_merge_and_validate_controls(self):
        chosen = settings("preview", {"samples": 64.0, "engine": "cpu", "motion_blur": True, "convert_materials": False})
        self.assertEqual((chosen["samples"], chosen["engine"], chosen["max_edge"]), (64, "cpu", 960))
        self.assertIs(type(chosen["samples"]), int)
        self.assertTrue(chosen["motion_blur"])
        self.assertIs(chosen["convert_materials"], False)
        self.assertNotIn("convert_materials", settings("final"))
        for changes, message in [({"samples": 0}, "integer"), ({"samples": 2.5}, "integer"),
                                 ({"engine": "gpu"}, "xpu, cpu"), ({"motion_blur": 1}, "true or false"),
                                 ({"convert_materials": "no"}, "true or false"),
                                 ({"denoiser": True}, "off, optix, oidn"), ({"time_limit": 3600}, "1..540"),
                                 ({"color_limit": float("nan")}, "number"), ({"exposure": 1}, "Supported")]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                settings("preview", changes)
        with self.assertRaisesRegex(ValueError, "Unknown preset"):
            settings("draft")

    def test_explicit_width_replaces_the_preset_edge_limit(self):
        self.assertNotIn("max_edge", settings("preview", {"width": 2000}))
        self.assertEqual(settings("preview", {"width": 2000, "max_edge": 1000})["max_edge"], 1000)
        saved = {"night": {"base": "standard", "changes": {"samples": 256, "denoiser": "oidn"}}}
        night = settings("night", {"engine": "cpu"}, saved)
        self.assertEqual((night["samples"], night["denoiser"], night["engine"], night["max_edge"]),
                         (256, "oidn", "cpu", 1920))

    def test_lighting_looks_fill_defaults_and_refuse_controls_they_ignore(self):
        self.assertIsNone(lighting(settings("preview")))
        day = lighting(settings("preview", {"lighting": "day", "light_angle": -90}))
        self.assertEqual((day["angle"], day["elevation"], day["exposure"], day["fill"], day["keep_scene_lights"]),
                         (-90., 35., 0., 0., False))
        night = lighting(settings("final", {"lighting": "night"}))
        self.assertEqual((night["angle"], night["keep_scene_lights"]), (-135., True))  # a three-quarter backlight
        overcast = lighting(settings("preview", {"lighting": "overcast", "light_angle": 120, "light_exposure": 1}))
        self.assertEqual(overcast["angle"], 120.)  # the hidden sun: that side of the sky is brighter
        self.assertNotIn("fill", overcast)
        for changes, message in [({"lighting": "sunset"}, "scene, day, overcast, night, studio"),
                                 ({"light_angle": 30}, "only apply with lighting"),
                                 ({"lighting": "scene", "keep_scene_lights": True}, "only apply with lighting"),
                                 ({"lighting": "overcast", "light_fill": -1}, "no key light"),
                                 ({"lighting": "day", "light_elevation": 95}, "0..90"),
                                 ({"lighting": "studio", "light_fill": 4}, "-3..3"),
                                 ({"lighting": "studio", "light_exposure": 7}, "-6..6")]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                settings("preview", changes)

    def test_resolution_follows_camera_aspect_and_limits(self):
        self.assertEqual(resolution((1280, 720), {"max_edge": 960}), (960, 540))
        self.assertEqual(resolution((720, 1280), {"max_edge": 960}), (540, 960))
        self.assertEqual(resolution((1280, 720), {"max_edge": 4096}), (1280, 720))
        self.assertEqual(resolution((1280, 720), {"resolution_scale": .5}), (640, 360))
        self.assertEqual(resolution((1280, 720), {"width": 2000}), (2000, 1125))
        self.assertEqual(resolution((1280, 720), {"resolution_scale": .05, "max_edge": 64}), (64, 36))
        with self.assertRaises(ValueError):
            resolution((0, 720), {})


class LogTests(unittest.TestCase):
    def test_completed_frame_with_mixed_devices(self):
        info = read_log(LOG)
        self.assertEqual(info["resolution"], [640, 360])
        self.assertEqual(info["husk_seconds"], 61.93)
        self.assertEqual(info["peak_memory"], "2.14 GiB")
        self.assertTrue(info["saved"] and info["gpu_verified"])
        self.assertFalse(info["time_limit_reached"])
        self.assertEqual([(d["type"], d["contribution_percent"]) for d in info["devices"]],
                         [("Optix", 64.0), ("EmbreeCPU", 35.0)])
        self.assertEqual(info["log_warnings"], ["Warning: Unable to find texture brick.rat"])

    def test_time_limit_and_idle_gpu(self):
        info = read_log(LOG.replace("64%", "0%"), LIMIT)
        self.assertTrue(info["time_limit_reached"])
        self.assertFalse(info["gpu_verified"])
        self.assertFalse(any("Segmentation" in w or w.startswith("+0x") for w in info["log_warnings"]))
        self.assertIn("Fatal error: Segmentation fault", excerpt("", LIMIT))
        self.assertNotIn("+0x", excerpt("", LIMIT))

    def test_progress_is_the_last_logged_percentage(self):
        self.assertIsNone(read_log(LOG)["progress_percent"])
        stalled = LOG.replace("[08:48:53] Warning", "[08:48:52]   0.0% Lap= 0:00:00.70 Left= 19:37:46\n"
                                                    "[08:48:53]   6.2% Lap= 0:00:08.18 Left= 0:02:02\n[08:48:53] Warning")
        self.assertEqual(read_log(stalled, LIMIT)["progress_percent"], 6.2)


read_hdr = karma_sky.read_hdr


class SequenceLogTests(unittest.TestCase):
    def test_frames_stop_at_the_first_gap_and_name_the_time_limited(self):
        names = ["render.0003.png", "render.0001.png", "render.0002.png", "render.0005.png", "husk.log", "render.png"]
        stderr = ("[08:48:01] Run time 2 exceeded file C:/job/render.0002.png\n"
                  "155100: Fatal error: Segmentation fault\n")
        self.assertEqual(frames_saved(names, 1, stderr),
                         [{"frame": 1, "file": "render.0001.png", "status": "completed"},
                          {"frame": 2, "file": "render.0002.png", "status": "time_limit"},
                          {"frame": 3, "file": "render.0003.png", "status": "completed"}])
        self.assertEqual(frames_saved(names, 4), [])
        self.assertEqual([r["frame"] for r in frames_saved(["render.10000.png", "render.9999.png"], 9999)], [9999, 10000])

    def test_devices_come_from_the_last_frame_and_warnings_from_all(self):
        second = LOG.replace("(1 of 1)", "(2 of 2)").replace("brick.rat", "tile.rat").replace("0:01:01.93", "0:01:03.5")
        info = read_sequence_log(LOG.replace("(1 of 1)", "(1 of 2)") + second)
        self.assertEqual([d["contribution_percent"] for d in info["devices"]], [64.0, 35.0])
        self.assertEqual(info["husk_seconds"], 63.5)
        self.assertEqual(info["log_warnings"], ["Warning: Unable to find texture brick.rat",
                                                "Warning: Unable to find texture tile.rat"])
        self.assertEqual(read_sequence_log(LOG)["devices"], read_log(LOG)["devices"])


class SkyTests(unittest.TestCase):
    LOOKING_NEG_Z = karma_sky.camera_frame((0., -.2, -1.), (0., 1., 0.))

    def close(self, a, b, places=6):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places)

    def test_directions_follow_the_camera(self):
        frame = self.LOOKING_NEG_Z
        self.close(karma_sky.toward(frame, 0, 0), (0, 0, 1))  # from behind the camera
        self.close(karma_sky.toward(frame, 90, 0), (1, 0, 0))  # from the picture's right
        self.close(karma_sky.toward(frame, 180, 0), (0, 0, -1))  # backlight
        self.close(karma_sky.toward(frame, 30, 90), (0, 1, 0))
        down = karma_sky.camera_frame((0., -1., 0.), (0., 0., -1.))
        self.close(karma_sky.toward(down, 90, 0), (1, 0, 0))
        # Environment pixels: top is up, the middle column faces -Z and three quarters across faces +X.
        self.close(karma_sky.direction(.5, .5), (0, 0, -1))
        self.close(karma_sky.direction(.75, .5), (1, 0, 0))
        self.close(karma_sky.direction(.3, 0.), (0, 1, 0))

    def test_colour_temperatures_and_sunlight(self):
        self.close(karma_sky.kelvin(6500.), (1, 1, 1))
        self.assertAlmostEqual(karma_sky.luminance(karma_sky.kelvin(3000.)), 1.)
        moon = karma_sky.kelvin(karma_sky.MOON_KELVIN)
        self.assertAlmostEqual(moon[2] / moon[0], 1.3, 1)  # pale blue, not saturated
        suns = [karma_sky.sunlight(e) for e in (60, 35, 10, 3)]
        warmth = [c[2] / c[0] for c, _ in suns]
        self.assertEqual(warmth, sorted(warmth, reverse=True))  # warmer as the sun sinks
        self.assertAlmostEqual(warmth[1], .75, 2)  # about 5400 K at the default 35 degrees
        self.assertEqual([b for _, b in suns], sorted((b for _, b in suns), reverse=True))  # and dimmer
        self.assertAlmostEqual(karma_sky.sunlight(90)[1], 1., 3)
        self.assertAlmostEqual(karma_sky.form_factor(2, 2, 3), .1233, 4)
        self.assertGreater(karma_sky.form_factor(200, 200, 1), .99)

    def test_cie_skies_follow_the_standard(self):
        sun = karma_sky.toward(self.LOOKING_NEG_Z, 0, 40)  # toward +Z

        def toward(azimuth, elevation):  # azimuth from the sun's side
            a, e = math.radians(azimuth), math.radians(elevation)
            return math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)
        zenith = karma_sky.cie("day", (0., 1., 0.), sun)
        # Clear sky (CIE 12): the horizon is about 2.3 times the zenith opposite the sun and 5 times beneath it,
        # and the darkest patch, about 0.65 of the zenith, lies some 80-90 degrees from the sun.
        self.assertAlmostEqual(karma_sky.cie("day", toward(180, 0), sun) / zenith, 2.35, delta=.1)
        self.assertAlmostEqual(karma_sky.cie("day", toward(0, 0), sun) / zenith, 4.8, delta=.3)
        darkest = min((karma_sky.cie("day", toward(a, e), sun), toward(a, e)) for a in range(0, 181, 5) for e in range(0, 90, 2))
        self.assertAlmostEqual(darkest[0] / zenith, .65, delta=.05)
        self.assertTrue(75 < math.degrees(karma_sky.gap(darkest[1], sun)) < 95)
        # Overcast (CIE 2): the zenith three times the horizon, and the horizon under the hidden sun brighter.
        side = (1., 0., 0.)
        self.assertAlmostEqual(karma_sky.cie("overcast", (0., 1., 0.), side) / karma_sky.cie("overcast", (0., 0., 1.), side), 3., delta=.05)
        self.assertTrue(1.5 < karma_sky.cie("overcast", toward(0, 0), sun) / karma_sky.cie("overcast", toward(180, 0), sun) < 1.9)

    def test_sky_images_match_their_levels(self):
        frame = self.LOOKING_NEG_Z
        step = 2 * math.pi / 64 * math.pi / 32
        for look, fill in (("day", 0.), ("day", -1.), ("overcast", 0.), ("night", 0.), ("night", 1.)):
            with self.subTest(look=look, fill=fill):
                lights = karma_sky.plan(look, frame, 30, 40, fill)
                sun = lights[0] if lights else {"toward": karma_sky.toward(frame, 30, 40), "elevation": 40}
                rows = karma_sky.sky_image(look, sun, fill=fill, width=64, height=32)
                seen = sum(karma_sky.luminance(c) * d[1] * math.sqrt(1 - d[1] ** 2) * step
                           for j, row in enumerate(rows) for i, c in enumerate(row)
                           for d in [karma_sky.direction((i + .5) / 64, (j + .5) / 32)] if d[1] > 0) / math.pi
                level = karma_sky.LEVELS[look]["sky"] * (karma_sky.sky_scale(40) if look == "day" else 1)
                self.assertAlmostEqual(seen, level * 2 ** fill, 6)
                self.assertEqual(len(set(rows[-1])), 1)  # plain ground looking straight down
                # Just below the horizon the sky hazes into the ground instead of a hard wall.
                self.assertGreater(karma_sky.luminance(rows[16][0]), karma_sky.luminance(rows[-1][0]))
        sun = karma_sky.plan("day", frame, 30, 40)[0]
        day = karma_sky.sky_image("day", sun, width=64, height=32)
        self.assertGreater(day[2][0][2] / day[2][0][0], day[15][0][2] / day[15][0][0])  # bluer overhead
        # The light it sheds into shadows stays a pale blue, not cyan.
        shade = [sum(c[k] * d[1] * math.sqrt(1 - d[1] ** 2) for j, row in enumerate(day) for i, c in enumerate(row)
                     for d in [karma_sky.direction((i + .5) / 64, (j + .5) / 32)] if d[1] > 0) for k in range(3)]
        self.assertTrue(1.3 < shade[2] / shade[0] < 2., shade)
        # Studio backdrop: neutral grey, brightest straight behind the subject, two stops darker at the corner.
        view = ((0., 0., -1.), math.radians(25.))
        self.close(karma_sky.sky_shape("studio", view[0], view=view), (1, 1, 1))
        corner = karma_sky.sky_shape("studio", (math.sin(math.radians(25.)), 0., -math.cos(math.radians(25.))), view=view)
        self.close(corner, (.25, .25, .25))
        studio = karma_sky.sky_image("studio", view=view, width=64, height=32)
        self.assertTrue(all(c[0] == c[1] == c[2] for row in studio for c in row))
        self.assertAlmostEqual(max(c[0] for row in studio for c in row), karma_sky.LEVELS["studio"]["backdrop"], delta=.015)

    def test_hdr_round_trip(self):
        rows = [[(1., .5, .25), (0., 0., 0.)], [(.003, .004, .01), (12., 3., 0.)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sky.hdr"
            karma_sky.write_hdr(path, rows)
            for row, back in zip(rows, read_hdr(path)):
                for c, b in zip(row, back):
                    for x, y in zip(c, b):
                        self.assertAlmostEqual(x, y, delta=max(x, y, 1e-6) * .01)

    def test_lights_turn_with_the_angle_and_follow_the_levels(self):
        frame = self.LOOKING_NEG_Z
        sun, = karma_sky.plan("day", frame, 90, 40)
        self.assertEqual(sun["name"], "SUN")
        self.assertGreater(sun["toward"][0], .7)  # camera-right
        self.assertEqual(karma_sky.plan("overcast", frame), [])
        moon, = karma_sky.plan("night", frame, -135, 30)
        self.assertAlmostEqual(2 * moon["intensity"] * karma_sky.luminance(moon["color"]), karma_sky.LEVELS["night"]["moon"])
        self.assertLess(moon["toward"][2], 0)  # behind the subject
        rig = {l["name"]: l for l in karma_sky.plan("studio", frame, 30, 45)}
        self.assertEqual(list(rig), ["KEY", "FILL", "RIM"])
        self.assertGreater(rig["KEY"]["toward"][0], 0)
        self.assertLess(rig["FILL"]["toward"][0], 0)  # the other side of the camera
        self.assertLess(rig["RIM"]["toward"][2], 0)  # behind the subject
        self.assertLess(rig["RIM"]["toward"][0], 0)  # on the shadow side
        key = rig["KEY"]
        self.assertAlmostEqual(key["intensity"] * karma_sky.AREA_GAIN * karma_sky.form_factor(*key["size"], key["distance"]),
                               karma_sky.LEVELS["studio"]["key"])
        brighter = {l["name"]: l for l in karma_sky.plan("studio", frame, 30, 45, fill=1)}
        self.assertAlmostEqual(brighter["FILL"]["intensity"], 2 * rig["FILL"]["intensity"])
        self.assertEqual(brighter["KEY"]["intensity"], rig["KEY"]["intensity"])
        turned = {l["name"]: l for l in karma_sky.plan("studio", frame, 75, 45)}
        for name in rig:
            # Turning the key turns the whole rig: every light keeps its angle to the others.
            self.assertAlmostEqual(karma_sky.dot(rig["KEY"]["toward"], rig[name]["toward"]),
                                   karma_sky.dot(turned["KEY"]["toward"], turned[name]["toward"]))
        self.assertGreater(rig["KEY"]["intensity"], rig["FILL"]["intensity"])


class GpuLoadTests(unittest.TestCase):
    def test_reads_nvidia_smi_and_explains_a_busy_card(self):
        reply = subprocess.CompletedProcess([], 0, stdout="97, 21371, 24564\n")
        with patch("hlab.karma.subprocess.run", return_value=reply):
            load = karma.gpu_load()
        self.assertEqual(load, {"utilization_percent": 97.0, "free_mib": 3193.0})
        self.assertEqual(len(karma.load_notes(load)), 2)
        self.assertEqual(karma.load_notes({"utilization_percent": 12.0, "free_mib": 9000.0}), [])
        with patch("hlab.karma.subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(karma.gpu_load())
        self.assertEqual(karma.load_notes(None), [])


class KillTreeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows does not end a child process with its parent")
    def test_ends_the_renderer_a_worker_started(self):
        from hlab.worker_pool import kill_tree
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "child.pid"
            script = ("import pathlib, subprocess, sys, time\n"
                      "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                      f"pathlib.Path({str(marker)!r}).with_suffix('.tmp').write_text(str(child.pid))\n"
                      f"pathlib.Path({str(marker)!r}).with_suffix('.tmp').replace({str(marker)!r})\n"
                      "time.sleep(120)\n")
            parent = subprocess.Popen([sys.executable, "-c", script])
            deadline = time.monotonic() + 30
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            child = marker.read_text()
            kill_tree(parent)
            for _ in range(50):
                # The "no tasks" notice is localised, so decode leniently.
                listed = subprocess.run(["tasklist", "/FI", f"PID eq {child}", "/NH"],
                                        capture_output=True).stdout.decode(errors="replace")
                if child not in listed.split():
                    break
                time.sleep(.1)
            self.assertNotIn(child, listed.split())
            self.assertIsNotNone(parent.poll())


def fake_run(job_requests, size=(64, 36), status="completed", progress=None, stop_after=None, timeouts=None):
    """stop_after: how many frames each request of a range saves before husk "stops" (0 raises, as the worker does)."""
    def worker(req, job, timeout=None):
        job_requests.append(req)
        if timeouts is not None:
            timeouts.append(timeout)
        if req["action"] == "karma_inspect":
            return {"cameras": []}
        (job / "husk.log").write_text(LOG, encoding="utf-8")
        chosen = req["settings"]
        if req.get("frames"):
            first, last = req["frames"]
            done = last - first + 1 if not stop_after else stop_after.pop(0)
            if done == 0:
                raise ValueError("Karma render failed: cudaErrorLaunchFailure")
            rows = []
            for frame in range(first, min(last, first + done - 1) + 1):
                Image.new("RGBA", size, (200, 40, 30, 255)).save(job / f"render.{frame:04d}.png")
                rows.append({"frame": frame, "file": f"render.{frame:04d}.png",
                             "status": "time_limit" if status == "time_limit" and frame == first else "completed"})
            outcome = {"frames": rows, "stopped": None if len(rows) == last - first + 1 else "cudaErrorLaunchFailure",
                       "frame": first}
        else:
            Image.new("RGBA", size, (200, 40, 30, 255)).save(job / "render.png")
            outcome = {"file": "render.png", "frame": req["frame"] or 12}
        return {**outcome, "log": "husk.log", "camera": req["camera"] or "/obj/CAM",
                "rop": "/out/HR_KARMA_PREVIEW", "temporary_rop": True, "resolution": list(size),
                "seconds": 3.5, "lights": 1, "notes": [], "materials": {"converted": [], "unconverted": []},
                "settings": {"engine": chosen.get("engine", "xpu"), "samples": chosen.get("samples", 32),
                             "denoiser": chosen.get("denoiser", "off"),
                             **{k: chosen[k] for k in ("lighting", "light_angle", "light_elevation", "light_fill") if k in chosen}},
                **read_log(LOG),
                **({"scene": {"overrides": [{"parm": p, "from": 0, "to": v, "was_animated": False}
                                            for p, v in req["scene"]["overrides"].items()],
                              "hidden": list(req["scene"]["hide"])}} if req.get("scene") else {}),
                "status": status, "progress_percent": progress}
    return worker


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": self.home.name})
        self.env.start()
        self.idle = patch("hlab.karma.gpu_load", return_value=None)
        self.idle.start()
        self.hip = Path(self.home.name) / "shot.hip"
        self.hip.write_bytes(b"HIP")

    def tearDown(self):
        self.idle.stop()
        self.env.stop()
        self.home.cleanup()

    def test_busy_gpu_and_a_stalled_time_limit_are_explained(self):
        requests = []
        busy = {"utilization_percent": 97.0, "free_mib": 3193.0}
        with patch("hlab.karma.gpu_load", return_value=busy), \
                patch("hlab.sop_lab.worker", fake_run(requests, status="time_limit", progress=6.2)):
            run, _ = karma.render(str(self.hip))
        self.assertEqual(requests[0]["preset"], "preview")
        self.assertEqual(run["gpu_load"], busy)
        self.assertEqual(len(run["notes"]), 3)
        self.assertIn("6.2%", run["notes"][0])
        self.assertIn("编译着色器", run["notes"][0])
        self.assertIn("97%", run["notes"][1])
        self.assertIn("约完成 6.2%", run["summary"])

    def test_scene_based_presets_ask_the_worker_for_the_project_rop(self):
        requests = []
        karma.save_preset("mine", "scene", {"samples": 64})
        with patch("hlab.sop_lab.worker", fake_run(requests)):
            karma.render(str(self.hip), preset="mine")
            karma.compare(str(self.hip), {"A": {"preset": "mine"}, "B": {"preset": "scene"}})
        self.assertEqual([r["preset"] for r in requests], ["scene", "scene", "scene"])

    def test_lighting_reaches_the_worker_and_the_summary(self):
        requests = []
        with patch("hlab.sop_lab.worker", fake_run(requests)):
            run, _ = karma.render(str(self.hip), changes={"lighting": "day", "light_angle": 30, "light_elevation": 20,
                                                          "light_fill": -1})
            data, _ = karma.compare(str(self.hip), {"阴天": {"lighting": "overcast"}, "原灯": {}})
        self.assertEqual(requests[0]["settings"]["lighting"], "day")
        self.assertIn("灯光日景（方向 30°，高 20°，补光 -1 档）", run["summary"])
        self.assertIn("灯光阴天", data["variants"]["阴天"]["summary"])
        self.assertNotIn("灯光", data["variants"]["原灯"]["summary"])
        self.assertIn("阴天", karma.caption("A", data["variants"]["阴天"]))
        self.assertEqual([l["name"] for l in karma.presets()["lighting"]], ["scene", "day", "overcast", "night", "studio"])
        saved = karma.save_preset("夜景出图", "standard", {"lighting": "night", "light_exposure": 1})
        self.assertEqual((saved["settings"]["lighting"], saved["settings"]["samples"]), ("night", 128))

    def test_saved_presets_round_trip(self):
        result = karma.save_preset("夜景", "standard", {"samples": 256, "color_limit": 4}, "deep blue")
        self.assertEqual((result["replaced"], result["settings"]["samples"], result["settings"]["max_edge"]),
                         (False, 256, 1920))
        listed = karma.presets()
        self.assertEqual([p["name"] for p in listed["builtin"]], ["preview", "standard", "final", "scene"])
        self.assertEqual(listed["saved"][0]["settings"]["color_limit"], 4.0)
        self.assertIn("samples", listed["controls"])
        self.assertTrue(karma.save_preset("夜景", "preview", {"samples": 8})["replaced"])
        for args, message in [(("preview", "standard", {"samples": 8}), "built-in"),
                              (("x", "standard", {}), "at least one"), (("x", "draft", {"samples": 8}), "Base")]:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, message):
                karma.save_preset(*args)

    def test_saved_width_presets_match_inline_overrides(self):
        camera = (1280, 720)
        cases = [({"width": 2000}, None, (2000, 1125)),
                 ({"width": 2000, "max_edge": 1000}, None, (1000, 562)),
                 ({"width": 2000}, {"samples": 64}, (2000, 1125)),
                 ({"width": 2000}, {"max_edge": 800}, (800, 450)),
                 ({"width": 2000, "max_edge": 1000}, {"width": 1600}, (1600, 900))]
        for saved_changes, temporary_changes, expected in cases:
            with self.subTest(saved=saved_changes, temporary=temporary_changes):
                stored = karma.save_preset("wide", "preview", saved_changes)
                inline = settings("preview", saved_changes)
                self.assertEqual(stored["settings"], inline)
                restored = settings("wide", temporary_changes, karma.saved_presets())
                if not temporary_changes:
                    self.assertEqual(restored, inline)
                self.assertEqual(resolution(camera, restored), expected)
                listed = next(p for p in karma.presets()["saved"] if p["name"] == "wide")
                self.assertEqual(listed["settings"], inline)

    def test_render_stores_image_record_and_evidence(self):
        from hlab.server import evidence
        requests = []
        with patch("hlab.sop_lab.worker", fake_run(requests)):
            run, image = karma.render(str(self.hip), preset="preview", changes={"samples": 48}, topic="Lookdev")
        self.assertEqual(requests[0]["action"], "karma_render")
        self.assertEqual((requests[0]["settings"]["samples"], requests[0]["settings"]["max_edge"]), (48, 960))
        self.assertTrue(run["hip_unchanged"])
        self.assertIn("显卡贡献 64%", run["summary"])
        stored = Path(run["path"])
        self.assertEqual(stored.parent, Path(self.home.name).resolve() / "images")
        self.assertTrue(Path(run["log"]).is_file())
        self.assertEqual(image.size, (64, 36))
        content = evidence(run["record"])
        self.assertEqual([c.type for c in content], ["text", "image"])
        self.assertEqual(json.loads(content[0].text)["image_id"], run["image_id"])

    def test_compare_keeps_one_shot_and_saves_a_comparison(self):
        from hlab.server import evidence
        requests = []
        with patch("hlab.sop_lab.worker", fake_run(requests, (100, 50))):
            data, sheet = karma.compare(str(self.hip), {"A": {"samples": 8}, "B": {"preset": "standard"}},
                                        zoom=[.25, .2, .75, .8], note="noise")
        self.assertEqual([r["camera"] for r in requests], ["", "/obj/CAM"])
        self.assertEqual([r["frame"] for r in requests], [None, 12])
        self.assertEqual(requests[1]["settings"]["samples"], 128)
        self.assertEqual(sheet.width, 1280)
        self.assertTrue(Path(data["sheet"]).is_file())
        self.assertEqual(data["kind"], "comparison")
        self.assertEqual(json.loads(evidence(data["id"], variant="B")[0].text)["variant"], "B")
        for variants, zoom, message in [({"A": {}}, None, "2–4"), ({"A": {}, "B": {"spp": 1}}, None, "Supported"),
                                        ({"A": {}, "B": {}}, [.5, .5, .4, .9], "zoom")]:
            with self.subTest(variants=variants), self.assertRaisesRegex(ValueError, message):
                karma.compare(str(self.hip), variants, zoom=zoom)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_karma_is_a_render_domain_recipe(self):
        from hlab.server import mcp
        group = (await mcp.call_tool("domain_recipe", {"domain": "render"})).structuredContent
        self.assertEqual([r["name"] for r in group["recipes"]], ["karma"])
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": home}):
            result = await mcp.call_tool("domain_recipe", {"action": "run", "name": "karma",
                                                           "arguments": {"action": "presets"}})
        self.assertEqual(json.loads(result.content[0].text)["builtin"][0]["name"], "preview")
