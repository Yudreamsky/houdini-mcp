"""Chaos Vantage engine and photoreal options without Houdini or Vantage: rules, arguments, logs, sky and routing."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hlab import karma, karma_sky, photoreal, vantage
from hlab.karma_spec import lighting, look_settings, settings

STILL_LOG = """16:19:16.337 [inf] Chaos Vantage v3.3.1 (build 4820191, hash e736d0bb)
16:19:19.461 [inf] Device #0: NVIDIA GeForce RTX 4090, 24138 MB (DevId=0x2684, SubSysId=0x88EF1043, LUID=77815)
16:19:25.343 [inf] Total initialization time: 9.01 seconds
16:19:26.024 [inf] Loaded 'scene' | 1 Lights | 4 Nodes | 4 Unique vertices | 2 Unique faces
16:19:26.886 [inf] HQ image rendered in 0.222 seconds (+0.015s to write file): C:\\job\\vantage\\frame.png
"""
SEQUENCE_LOG = """16:37:39.503 [inf] Chaos Vantage v3.3.1 (build 4820191, hash e736d0bb)
16:37:48.608 [inf] Total initialization time: 9.11 seconds
16:37:49.349 [inf] Loaded 'scene' | 1 Lights | 31 Nodes | 81.02 thousand Unique vertices | 159.09 thousand Unique faces
16:39:44.163 [inf] Complete HQ sequence of 121 frames rendered in 1m 55s
16:39:44.200 [err] Texture not found: brick.png
"""
VIEW = {"projection": "perspective", "aspect": .5, "tan_half": .5,
        "matrices": {"1": [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]}}


class PhotorealTests(unittest.TestCase):
    def test_real_materials_pass(self):
        for m in ({"base_color": (.8, .08, .06), "metalness": 0., "roughness": .3, "specular": 1.},
                  {"base_color": (.95, .64, .54), "metalness": 1., "roughness": .1},
                  {"base_color": (1., 1., 1.), "transmission": 1., "roughness": .02, "specular": 1.}):
            with self.subTest(m=m):
                self.assertEqual(photoreal.issues(m), [])

    def test_unreal_values_are_named_and_fixed(self):
        cases = [({"base_color": (1., 1., 1.)}, "too_bright", {"base_color": (.85, .85, .85)}),
                 ({"base_color": (.01, .01, .01)}, "too_dark", {"base_color": (.03, .03, .03)}),
                 ({"base_color": (.2, .2, .2), "metalness": 1.}, "dark_metal", {"base_color": (.5, .5, .5)}),
                 ({"specular": 0.}, "no_reflection", {"specular": 1.}),
                 ({"roughness": 0.}, "mirror_smooth", {"roughness": .05})]
        for m, code, expected in cases:
            with self.subTest(code=code):
                self.assertEqual([c for c, _ in photoreal.issues(m)], [code])
                out, changes = photoreal.fixed(m)
                self.assertEqual(len(changes), 1)
                for key, value in expected.items():
                    if isinstance(value, tuple):
                        for x, y in zip(out[key], value):
                            self.assertAlmostEqual(x, y)
                    else:
                        self.assertAlmostEqual(out[key], value)

    def test_half_metal_is_reported_but_left_alone(self):
        m = {"base_color": (.6, .6, .6), "metalness": .5}
        self.assertIn("half_metal", [c for c, _ in photoreal.issues(m)])
        self.assertEqual(photoreal.fixed(m), (m, []))

    def test_colour_keeps_its_hue_when_brightness_is_corrected(self):
        out, _ = photoreal.fixed({"base_color": (1., .5, .25)})
        self.assertAlmostEqual(out["base_color"][1] / out["base_color"][0], .5)
        self.assertAlmostEqual(max(out["base_color"]), photoreal.BRIGHT_TARGET)


class SettingsTests(unittest.TestCase):
    def test_vantage_keeps_shared_controls_and_drops_karma_ones(self):
        chosen = settings("standard", {"engine": "vantage", "round_edges": 2, "pbr_fix": True, "lighting": "day"})
        self.assertEqual((chosen["engine"], chosen["samples"], chosen["max_edge"]), ("vantage", 128, 1920))
        self.assertNotIn("time_limit", chosen)
        self.assertEqual((chosen["round_edges"], chosen["pbr_fix"]), (2., True))
        for preset, changes, message in [("scene", {"engine": "vantage"}, "preset scene"),
                                         ("preview", {"engine": "vantage", "time_limit": 30}, "only apply to Karma"),
                                         ("preview", {"engine": "vantage", "convert_materials": False}, "only apply"),
                                         ("preview", {"round_edges": 120}, "0..100"),
                                         ("preview", {"pbr_fix": 1}, "true or false")]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                settings(preset, changes)

    def test_look_settings_report_every_light_control(self):
        self.assertEqual(look_settings(None), {"lighting": "scene"})
        day = look_settings(lighting({"lighting": "day", "light_fill": -1}))
        self.assertEqual((day["lighting"], day["light_angle"], day["light_elevation"], day["light_fill"]), ("day", 30., 35., -1))
        self.assertNotIn("light_fill", look_settings(lighting({"lighting": "overcast"})))


class CommandLineTests(unittest.TestCase):
    def test_still_sequence_and_orthographic_arguments(self):
        chosen = {"samples": 128, "denoiser": "off", "motion_blur": True}
        still = vantage.arguments("s.usd", "o.png", (640, 360), "CAM", chosen, VIEW, "v.log")
        self.assertIn("-samples=128", still)
        self.assertIn("-denoiser=false", still)
        self.assertIn("-motionBlur=true", still)
        self.assertIn("-camera=CAM", still)
        self.assertFalse([a for a in still if a.startswith(("-frames", "-cameraType"))])
        sequence = vantage.arguments("s.usd", "o.png", (640, 360), "CAM", {}, VIEW, "v.log", frames=31)
        self.assertIn("-frames=0-30", sequence)
        self.assertIn("-antiFlicker=true", sequence)
        self.assertIn("-denoiser=true", sequence)
        ortho = vantage.arguments("s.usd", "o.png", (640, 360), "CAM", {}, {**VIEW, "projection": "orthographic",
                                                                            "ortho_width": 15.65}, "v.log")
        self.assertIn("-cameraType=5", ortho)
        self.assertIn("-cameraOrthoWidth=15.65", ortho)

    def test_logs_give_timings_scene_and_errors(self):
        still = vantage.read_log(STILL_LOG)
        self.assertEqual((still["vantage_version"], still["gpu"]), ("3.3.1", "NVIDIA GeForce RTX 4090"))
        self.assertEqual((still["startup_seconds"], still["render_seconds"]), (9.01, .222))
        self.assertEqual(still["scene"], {"lights": 1, "nodes": 4, "vertices": 4})
        self.assertNotIn("log_errors", still)
        sequence = vantage.read_log(SEQUENCE_LOG)
        self.assertEqual((sequence["frames_rendered"], sequence["render_seconds"]), (121, 115))
        self.assertEqual(sequence["scene"]["vertices"], 81020)
        self.assertEqual(sequence["log_errors"], ["Texture not found: brick.png"])
        self.assertEqual([vantage.minutes(t) for t in ("0m 3s", "1m 55s", "42s", "soon")], [3, 115, 42, None])
        self.assertEqual(vantage.summary_seconds({**still, "export_seconds": .6}), "（渲染 0.222 秒，启动 9.01 秒，导出 0.6 秒）")

    def test_start_up_crashes_are_retried_then_reported(self):
        class Process:
            def __init__(self, code):
                self.code = code

            def wait(self, timeout):
                return self.code

        with patch("hlab.vantage.executable", return_value=Path("vantage_console.exe")):
            with patch("subprocess.Popen", side_effect=[Process(3221225477), Process(0)]):
                self.assertEqual(vantage.launch([], 10), 2)
            with patch("subprocess.Popen", side_effect=[Process(3221225477)] * 3), \
                    self.assertRaisesRegex(RuntimeError, "on all 3 tries"):
                vantage.launch([], 10)
            with patch("subprocess.Popen", side_effect=[Process(1)]), self.assertRaisesRegex(RuntimeError, "exit code 1$"):
                vantage.launch([], 10)

    def test_missing_vantage_is_explained(self):
        with patch.dict(os.environ, {"HOUDINI_RESEARCH_VANTAGE": "Z:/nowhere/vantage_console.exe"}), \
                self.assertRaisesRegex(ValueError, "not installed"):
            vantage.executable()


class SkyTests(unittest.TestCase):
    def test_lookup_inverts_the_sky_image_layout(self):
        width, height = 16, 8
        rows = [[(float(i), float(j), 0.) for i in range(width)] for j in range(height)]
        for i, j in ((0, 0), (5, 3), (15, 7), (8, 4)):
            got = karma_sky.lookup(rows, karma_sky.direction((i + .5) / width, (j + .5) / height))
            self.assertAlmostEqual(got[0], i, 6)
            self.assertAlmostEqual(got[1], j, 6)

    def test_backdrop_looks_where_the_camera_looks(self):
        # Bright above the horizon, dark below: a level camera sees the horizon across the middle.
        rows = [[(1., 1., 1.) if j < 4 else (0., 0., 0.)] * 8 for j in range(8)]
        back = vantage.backdrop(rows, VIEW, 1, (64, 32))
        self.assertGreater(back.getpixel((32, 2))[0], 200)
        self.assertLess(back.getpixel((32, 29))[0], 60)
        flat = vantage.backdrop(rows, {**VIEW, "projection": "orthographic"}, 1, (8, 4))
        self.assertEqual(len(flat.getcolors()), 1)

    def test_edges_blend_as_premultiplied_linear_colour(self):
        sky = [[(.5, .5, .5)] * 8 for _ in range(8)]
        with tempfile.TemporaryDirectory() as tmp:
            picture = Path(tmp) / "frame.png"
            front = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
            # Linear 0.25 at half cover: the object's half of a 0.5 grey pixel.
            front.putpixel((1, 0), (vantage.srgb(.25),) * 3 + (128,))
            front.putpixel((2, 0), (200, 10, 10, 255))
            front.save(picture)
            out = vantage.with_sky(picture, sky, {**VIEW, "projection": "orthographic"}, 1)
        grey = vantage.srgb(.5)
        self.assertEqual(out.getpixel((0, 0)), (grey,) * 3)
        self.assertEqual(out.getpixel((2, 0)), (200, 10, 10))
        self.assertTrue(all(abs(c - vantage.srgb(.25 + .5 * 127 / 255)) <= 1 for c in out.getpixel((1, 0))))


def fake_export(requests, frames=1):
    def worker(req, job):
        requests.append(req)
        return {"usd": "scene.usd", "camera": req["camera"] or "/obj/CAM", "camera_name": "CAM",
                "frames": req["frames"] or [7, 7], "resolution": [64, 36], "view": VIEW, "sky": None,
                "lighting": None, "materials": {"converted": [{"material": "/mat/a"}], "unconverted": []},
                "photoreal": {"pbr_fixes": [{"material": "/mat/a", "changes": ["加上 4% 的反射"]}],
                              "round_edges": {"millimetres": 2., "objects": 1, "failed": []}},
                "lights": 2, "normals_added": 1, "usd_edits": {}, "export_seconds": .6, "notes": ["导出说明"]}
    return worker


def fake_vantage(count):
    def run(job, info, chosen, frames=0):
        out = job / "vantage"
        out.mkdir()
        pictures = []
        for i in range(max(frames, 1)):
            pictures.append(out / f"frame.{i:05d}.png")
            Image.new("RGB", (64, 36), (20 * i % 255, 90, 160)).save(pictures[-1])
        log = SEQUENCE_LOG if frames else STILL_LOG
        (job / "vantage.log").write_text(log, encoding="utf-8")
        count.append(frames)
        return pictures, log, 2
    return run


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.patches = [patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": self.home.name}),
                        patch("hlab.karma.gpu_load", return_value=None),
                        patch("hlab.vantage.executable", return_value=Path("vantage_console.exe"))]
        for p in self.patches:
            p.start()
        self.hip = Path(self.home.name) / "shot.hip"
        self.hip.write_bytes(b"HIP")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.home.cleanup()

    def test_vantage_still_reads_like_a_karma_render(self):
        requests, runs = [], []
        with patch("hlab.sop_lab.worker", fake_export(requests)), patch("hlab.vantage.run", fake_vantage(runs)):
            run, image = karma.render(str(self.hip), changes={"engine": "vantage", "round_edges": 2, "pbr_fix": True},
                                      topic="lookdev")
        self.assertEqual((requests[0]["action"], requests[0]["frames"]), ("vantage_export", None))
        self.assertEqual(runs, [0])
        self.assertEqual((run["frame"], run["status"], run["gpu_verified"], run["vantage_tries"]), (7, "completed", True, 2))
        self.assertEqual(run["settings"]["engine"], "vantage")
        self.assertEqual((run["render_seconds"], run["startup_seconds"], run["export_seconds"]), (.222, 9.01, .6))
        self.assertIn("（渲染 0.222 秒，启动 9.01 秒，导出 0.6 秒）", run["summary"])
        self.assertIn("圆角 2 毫米", run["summary"])
        self.assertIn("按真实材料改正 1 个材质", run["summary"])
        self.assertIn("崩溃了 1 次", " ".join(run["notes"]))
        self.assertTrue(Path(run["path"]).is_file() and Path(run["log"]).is_file())
        self.assertIn("渲染 0.222", karma.caption("V", run))
        self.assertEqual(image.size, (64, 36))
        self.assertIn("record", run)

    def test_engines_compare_on_one_shot(self):
        requests = []
        from tests.test_karma import fake_run

        def worker(req, job):
            return (fake_export if req["action"] == "vantage_export" else lambda r: fake_run(r))(requests)(req, job)

        with patch("hlab.sop_lab.worker", worker), patch("hlab.vantage.run", fake_vantage([])):
            data, _ = karma.compare(str(self.hip), {"Karma": {"engine": "xpu"}, "Vantage": {"engine": "vantage"}})
        self.assertEqual([r["action"] for r in requests], ["karma_render", "vantage_export"])
        self.assertEqual(requests[1]["frames"], [12, 12])
        self.assertEqual(requests[1]["camera"], "/obj/CAM")
        self.assertIn("Vantage", data["variants"]["Vantage"]["summary"])

    def test_vantage_animation_renders_the_range_in_one_run(self):
        requests, runs = [], []
        with patch("hlab.sop_lab.worker", fake_export(requests)), patch("hlab.vantage.run", fake_vantage(runs)), \
                patch("hlab.vantage.encode", side_effect=lambda folder, pattern, fps, target: target):
            run, sheet = karma.animate(str(self.hip), "", [1001, 1005], changes={"engine": "vantage"}, fps=25,
                                       topic="crane")
        self.assertEqual((requests[0]["frames"], runs), ([1001, 1005], [5]))
        self.assertEqual((run["frame_count"], run["fps"], run["frames"]), (5, 25, [1001, 1005]))
        frames = sorted(Path(run["frames_folder"]).glob("f*.png"))
        self.assertEqual([f.name for f in frames], [f"f{i:04d}.png" for i in range(1, 6)])
        self.assertTrue(run["video"].endswith("clip.mp4"))
        self.assertIn("5 帧，25 帧/秒", run["summary"])
        self.assertEqual(sheet.size, (3 * 426, 30 + 240))
        self.assertIn("record", run)

    def test_karma_animation_and_limits(self):
        requests = []
        from tests.test_karma import fake_run
        with patch("hlab.sop_lab.worker", fake_run(requests)), patch("hlab.vantage.encode", return_value=None):
            run, _ = karma.animate(str(self.hip), "", [1, 3])
        self.assertEqual([r["frame"] for r in requests], [1, 2, 3])
        self.assertEqual([r["camera"] for r in requests], ["", "/obj/CAM", "/obj/CAM"])
        self.assertEqual((run["frame_count"], run["seconds"], run["video"]), (3, 10.5, None))
        self.assertIn("ffmpeg", run["notes"][-1])
        for frames, changes, fps, message in [([5, 1], {}, 24, "first, last"), ([1, 60], {}, 24, "48"),
                                              ([1, 600], {"engine": "vantage"}, 24, "480"), ([1.5, 3], {}, 24, "whole"),
                                              ([1, 3], {}, 0, "fps")]:
            with self.subTest(frames=frames, fps=fps), self.assertRaisesRegex(ValueError, message):
                karma.animate(str(self.hip), "", frames, changes=changes, fps=fps)


if __name__ == "__main__":
    unittest.main()
