import json
import unittest

from examples.wfc.rules import maze_request
from hlab.server import mcp
from hlab.wfc import solve


class WfcDomainTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_routed_execution_coexist_with_render(self):
        visible = {tool.name for tool in await mcp.list_tools()}
        self.assertEqual(len(visible), 15)
        self.assertNotIn("wfc_layout", visible)
        self.assertNotIn("karma", visible)
        domains = (await mcp.call_tool("domain_recipe", {})).structuredContent["domains"]
        self.assertEqual(domains["procedural-modeling"], ["wfc_layout"])
        self.assertEqual(domains["render"], ["karma"])
        item = (await mcp.call_tool("domain_recipe", {"name": "wfc_layout"})).structuredContent
        self.assertTrue(item["annotations"]["readOnlyHint"])
        self.assertIn("connected_socket", item["inputSchema"]["properties"])
        request = maze_request(4)
        routed = await mcp.call_tool("domain_recipe", dict(action="run", domain="procedural-modeling",
                                                          name="wfc_layout", arguments=request))
        self.assertFalse(routed.isError)
        result = routed.structuredContent or json.loads(routed.content[0].text)
        self.assertEqual(result, solve(**request))

    async def test_routed_validation_and_conflict_diagnostics(self):
        basic = dict(name="A", west="j", east="j", south="j", north="j")
        query = dict(columns=1, rows=1, tiles=[basic])
        routed = await mcp.call_tool("domain_recipe", dict(action="run", name="wfc_layout", arguments=query))
        self.assertEqual(json.loads(routed.content[0].text)["layout"], [["A"]])
        for args, message in (
            (dict(query, columns=0), "1 to 256"),
            (dict(query, tiles=[dict(basic, typo=1)]), "Additional properties"),
            (dict(query, columns="2"), "integer"),
            (dict(query, loop_free=True), "requires a connected_socket"),
            (dict(query, edges=dict(west="blocked", east="j", south="j", north="j")), "cell \\(0, 0\\)"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(Exception, message):
                await mcp.call_tool("domain_recipe", dict(action="run", name="wfc_layout", arguments=args))
