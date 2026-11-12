import unittest
from unittest.mock import patch

from PIL import Image
from mcp.server.fastmcp import FastMCP

from hlab.catalog import DOMAIN_OF, ResearchMCP
from hlab.server import mcp


class DomainCatalogTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_fireworks_recipe_tool_is_a_domain_recipe_and_node_lab_asks_for_its_node(self):
        from hlab import server
        visible = {t.name for t in await mcp.list_tools()}
        self.assertNotIn("recipe", visible)  # it only works on the fireworks fixture
        group = (await mcp.call_tool("domain_recipe", {"domain": "fireworks"})).structuredContent
        self.assertIn("recipe", [r["name"] for r in group["recipes"]])
        with self.assertRaisesRegex(ValueError, "Use save with a title"):  # still reachable by its old name
            server.recipe(action="list")
        for action in ("inspect", "nodes", "sweep", "compare", "motion", "variant"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, f"node_lab {action} needs node"):
                server.node_lab(action=action, hip="scene.hip")
        with self.assertRaisesRegex(ValueError, "scene_recipe to restore"):  # restore takes its node from the key
            server.node_lab(action="restore")

    async def test_lazy_lists_and_original_schema(self):
        visible = {t.name for t in await mcp.list_tools()}
        self.assertLessEqual(len(visible), 17)
        self.assertTrue(
            {"domain_recipe", "window_session", "node_lab", "knowledge", "fx_watch"} <= visible
        )
        self.assertTrue(visible.isdisjoint(DOMAIN_OF))
        raw = {t.name: t for t in await FastMCP.list_tools(mcp)}
        for name in ("node_types", "graph_read", "cook", "capture", "diff"):
            self.assertTrue(raw[name].annotations.readOnlyHint, name)
        self.assertTrue(raw["graph_edit"].annotations.destructiveHint)
        domains = (await mcp.call_tool("domain_recipe", {})).structuredContent["domains"]
        self.assertEqual({n for ns in domains.values() for n in ns}, set(DOMAIN_OF) & raw.keys())
        for domain, names in domains.items():
            group = (await mcp.call_tool("domain_recipe", {"domain": domain})).structuredContent
            self.assertEqual([r["name"] for r in group["recipes"]], list(names))
            self.assertTrue(all("inputSchema" not in item for item in group["recipes"]))
            for name in names:
                entry = (await mcp.call_tool("domain_recipe", {"name": name})).structuredContent
                self.assertEqual(entry["inputSchema"], raw[name].inputSchema)
                self.assertEqual(entry["description"], raw[name].description)

    async def test_proxy_accepts_only_allowlisted_schema_valid_requests(self):
        with patch("hlab.server.call") as bridge:
            for args, expected in [
                ({"name": "session", "arguments": {"initialize": "false"}}, "boolean"),
                ({"name": "session", "arguments": {"typo": True}}, "unknown argument"),
                ({"name": "knowledge"}, "Unknown domain recipe"),
                ({"name": "domain_recipe"}, "Unknown domain recipe"),
                ({"domain": "mechanics", "name": "observe"}, "Unknown domain recipe"),
                ({"name": "mechanism", "arguments": {"hip": "rain"}}, "required property"),
            ]:
                with self.subTest(args=args), self.assertRaisesRegex(Exception, expected):
                    await mcp.call_tool("domain_recipe", {"action": "run", **args})
            bridge.assert_not_called()

    async def test_images_and_structured_results_survive_routing(self):
        with (
            patch("hlab.server.call", return_value={"frame": 24}),
            patch("hlab.server.viewport_image", return_value=Image.new("RGB", (3, 2))),
        ):
            direct = await mcp.call_tool("observe", {"frame": 24})
            routed = await mcp.call_tool(
                "domain_recipe", {"action": "run", "name": "observe", "arguments": {"frame": 24}}
            )
            self.assertEqual(routed.content, direct)
            self.assertEqual([b.type for b in routed.content], ["text", "image"])
            self.assertIsNone(routed.structuredContent)
        fixture = ResearchMCP("catalog test")

        @fixture.tool()
        def session() -> dict[str, int]:
            return {"frame": 24}

        listed = await fixture.domain_recipe("catalog", "", "", None)
        self.assertEqual(listed.structuredContent, {"domains": {"fireworks": ["session"]}})
        direct_text, direct_data = await fixture.call_tool("session", {})
        routed = await fixture.domain_recipe("run", "", "session", {})
        self.assertEqual(routed.structuredContent, direct_data)
        self.assertEqual(routed.content, direct_text)
