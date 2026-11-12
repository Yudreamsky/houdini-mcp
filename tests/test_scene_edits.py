"""Temporary scene edits for one render: parameter overrides and hidden objects, without Houdini."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hlab import karma
from hlab.karma_spec import checked_scene
from tests.test_karma import fake_run

WIND = "/obj/WIND/STATE/strength"


class RuleTests(unittest.TestCase):
    def test_edits_are_paths_and_plain_values(self):
        self.assertIsNone(checked_scene())
        self.assertIsNone(checked_scene({}, []))
        self.assertEqual(checked_scene({WIND: 1.5, "/obj/A/on": True, "/obj/A/label": "x"}, ["/obj/B", "/obj/B"]),
                         {"overrides": {WIND: 1.5, "/obj/A/on": True, "/obj/A/label": "x"}, "hide": ["/obj/B"]})
        for overrides, hide, message in [({"strength": 1}, None, "absolute parameter paths"),
                                         ({"/strength": 1}, None, "absolute parameter paths"),
                                         ({WIND: None}, None, "finite numbers"),
                                         ({WIND: float("inf")}, None, "finite numbers"),
                                         ({WIND: [1, 2]}, None, "finite numbers"),
                                         (None, ["BOX"], "absolute object paths"),
                                         ([WIND], None, "overrides is an object"),
                                         (None, "/obj/BOX", "hide is a list"),
                                         ({f"/obj/n/p{i}": i for i in range(65)}, None, "at most 64")]:
            with self.subTest(overrides=overrides, hide=hide), self.assertRaisesRegex(ValueError, message):
                checked_scene(overrides, hide)


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.patches = [patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": self.home.name}),
                        patch("hlab.karma.gpu_load", return_value=None), patch("hlab.vantage.encode", return_value=None)]
        for p in self.patches:
            p.start()
        self.hip = Path(self.home.name) / "shot.hip"
        self.hip.write_bytes(b"HIP")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.home.cleanup()

    def test_a_render_carries_its_edits_to_the_worker_the_summary_and_the_record(self):
        requests = []
        with patch("hlab.sop_lab.worker", fake_run(requests)):
            plain, _ = karma.render(str(self.hip))
            run, _ = karma.render(str(self.hip), topic="wind", overrides={WIND: 1}, hide=["/obj/BACKDROP"])
        self.assertNotIn("scene", requests[0])
        self.assertEqual(requests[1]["scene"], {"overrides": {WIND: 1}, "hide": ["/obj/BACKDROP"]})
        self.assertNotIn("场景参数", plain["summary"])
        self.assertIn("临时改 1 个场景参数，隐藏 1 个物体", run["summary"])
        from hlab.storage import details
        self.assertEqual(details(run["record"])["details"]["scene"], requests[1]["scene"])

    def test_compare_variants_add_their_own_edits_to_the_shared_ones(self):
        requests = []
        variants = {"calm": {"overrides": {WIND: 0}}, "windy": {"samples": 64, "overrides": {WIND: 1}, "hide": ["/obj/BOX"]}}
        with patch("hlab.sop_lab.worker", fake_run(requests)):
            card, _ = karma.compare(str(self.hip), variants, overrides={"/obj/SUN/ry": 30}, hide=["/obj/BACKDROP"])
        self.assertEqual([r["scene"] for r in requests],
                         [{"overrides": {"/obj/SUN/ry": 30, WIND: 0}, "hide": ["/obj/BACKDROP"]},
                          {"overrides": {"/obj/SUN/ry": 30, WIND: 1}, "hide": ["/obj/BACKDROP", "/obj/BOX"]}])
        self.assertEqual(requests[1]["settings"]["samples"], 64)  # the edits are not render controls
        self.assertEqual(len(card["variants"]["windy"]["scene"]["overrides"]), 2)

    def test_an_animation_passes_its_edits_to_every_run(self):
        requests = []
        with patch("hlab.sop_lab.worker", fake_run(requests)), patch("hlab.karma.CHUNK", 2):
            run, _ = karma.animate(str(self.hip), "", [1, 3], overrides={WIND: 1})
        self.assertEqual([r["frames"] for r in requests], [[1, 2], [3, 3]])
        self.assertTrue(all(r["scene"] == {"overrides": {WIND: 1}, "hide": []} for r in requests))
        self.assertIn("临时改 1 个场景参数", run["summary"])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_karma_recipe_accepts_overrides_hide_and_variant_edits(self):
        from hlab import server
        seen = []

        def render(*args):
            seen.append(args)
            return {"status": "completed"}, Image.new("RGB", (4, 4))

        with patch("hlab.karma.render", render), patch("hlab.karma.compare", render):
            await server.mcp.call_tool("domain_recipe", {"action": "run", "name": "karma", "arguments": {
                "action": "render", "hip": "shot.hip", "overrides": {WIND: 1.5}, "hide": ["/obj/BOX"]}})
            await server.mcp.call_tool("domain_recipe", {"action": "run", "name": "karma", "arguments": {
                "action": "compare", "hip": "shot.hip",
                "variants": {"A": {"overrides": {WIND: 0}}, "B": {"samples": 64, "hide": ["/obj/BOX"]}}}})
        self.assertEqual(seen[0][-2:], ({WIND: 1.5}, ["/obj/BOX"]))
        self.assertEqual(seen[1][1], {"A": {"overrides": {WIND: 0}}, "B": {"samples": 64, "hide": ["/obj/BOX"]}})


if __name__ == "__main__":
    unittest.main()
