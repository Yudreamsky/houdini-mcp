import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hlab import karma
from hlab.karma_spec import excerpt, read_log, resolution, settings

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


def fake_run(job_requests, size=(64, 36)):
    def worker(req, job):
        job_requests.append(req)
        if req["action"] == "karma_inspect":
            return {"cameras": []}
        Image.new("RGBA", size, (200, 40, 30, 255)).save(job / "render.png")
        (job / "husk.log").write_text(LOG, encoding="utf-8")
        chosen = req["settings"]
        return {"file": "render.png", "log": "husk.log", "frame": req["frame"] or 12, "camera": req["camera"] or "/obj/CAM",
                "rop": "/out/HR_KARMA_PREVIEW", "temporary_rop": True, "resolution": list(size), "status": "completed",
                "seconds": 3.5, "lights": 1, "notes": [], "materials": {"converted": [], "unconverted": []},
                "settings": {"engine": chosen.get("engine", "xpu"), "samples": chosen.get("samples", 32),
                             "denoiser": chosen.get("denoiser", "off")}, **read_log(LOG)}
    return worker


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": self.home.name})
        self.env.start()
        self.hip = Path(self.home.name) / "shot.hip"
        self.hip.write_bytes(b"HIP")

    def tearDown(self):
        self.env.stop()
        self.home.cleanup()

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
