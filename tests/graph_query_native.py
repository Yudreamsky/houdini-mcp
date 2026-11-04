"""Run in a fresh hython. Every writable research record belongs to the temporary library."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import hou

from hlab.graph_query import cook, diff, graph_read, node_types
from hlab.scene import load_checkpoint
from hlab.storage import details, stored


class NativeGraphTests(unittest.TestCase):
    def setUp(self):
        self.library = self.enterContext(tempfile.TemporaryDirectory(prefix="graph-query-test-"))
        self.enterContext(patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": self.library}))
        self.obj = hou.node("/obj")
        self.frame = hou.frame()
        self.addCleanup(hou.setFrame, self.frame)

    def test_native_types_links_parameters_cook_and_snapshot(self):
        first = node_types("sop", "scatter", limit=1)
        names = [
            node["name"]
            for node in first["items"] + node_types("sop", "scatter", offset=1, limit=100)["items"]
        ]
        self.assertEqual(len(names), first["total"])
        self.assertIn("scatter::2.0", names)
        self.assertEqual(node_types("obj", "geo")["category"], "Object")
        with self.assertRaises(ValueError):
            node_types("no_such_context")

        geo = self.obj.createNode("geo", run_init_scripts=False)
        self.addCleanup(geo.destroy)
        source = geo.createNode("box", "SOURCE")
        out = source.createOutputNode("xform", "SHIFT")
        retired = geo.createNode("null", "RETIRED")
        source.parm("sizex").set(3.0)
        source.parm("sizex").lock(True)
        source.parm("sizey").setExpression("$F")
        out.parm("tx").setExpression('ch("../SOURCE/sizex")')
        for frame, value in [(1, 0.0), (5, 8.0)]:
            k = hou.Keyframe()
            k.setFrame(frame)
            k.setValue(value)
            out.parm("ty").setKeyframe(k)
        out.setDisplayFlag(True)
        snap = graph_read(geo.path(), limit=1, snapshot=True)
        self.assertEqual((len(snap["nodes"]), snap["total"], snap["next_offset"]), (1, 3, 1))
        rows = graph_read(geo.path())["nodes"]
        by_name = {row["relative"]: row for row in rows}
        self.assertEqual(by_name["SHIFT"]["inputs"], [{"input": 0, "source": "SOURCE", "output": 0}])
        self.assertTrue(by_name["SHIFT"]["flags"]["display"])
        self.assertTrue(by_name["SOURCE"]["parameters"]["sizex"]["locked"])
        self.assertNotIn("sizez", by_name["SOURCE"]["parameters"])
        self.assertEqual(by_name["SHIFT"]["parameters"]["tx"]["reference"], "../SOURCE/sizex")
        self.assertEqual(len(by_name["SHIFT"]["parameters"]["ty"]["value"]), 2)
        self.assertTrue(by_name["SHIFT"]["parameters"]["ty"]["animated"])
        self.assertEqual(by_name["SOURCE"]["parameters"]["sizey"]["expression"]["text"], "$F")
        self.assertEqual(diff(snap["snapshot"])["total_changed"], 0)
        report = cook(out.path(), 3)
        self.assertEqual((report["points"], report["primitives"], report["errors"]), (8, 6, []))
        self.assertEqual(report["attributes"]["point"][0]["name"], "P")
        self.assertAlmostEqual(report["bounds"]["max"][1] - report["bounds"]["min"][1], 3.0)
        self.assertEqual(hou.frame(), self.frame)
        self.assertEqual(cook(geo.path())["geometry_node"], out.path())
        retired.destroy()
        new = geo.createNode("grid", "REPLACEMENT")
        out.setInput(0, new)
        source.parm("sizez").set(5)
        delta = diff(snap["snapshot"])
        self.assertEqual(delta["added"], ["REPLACEMENT"])
        self.assertEqual(delta["removed"], ["RETIRED"])
        changes = {row["relative"]: row for row in delta["changed"]}
        self.assertEqual(changes["SHIFT"]["inputs"]["after"][0]["source"], "REPLACEMENT")
        self.assertEqual(changes["SOURCE"]["parameters"]["sizez"]["after"]["value"], 5.0)
        broken = geo.createNode("file")
        broken.parm("file").set(str(Path(self.library) / "missing.bgeo.sc"))
        self.assertTrue(cook(broken.path())["errors"])

    def test_nested_subnet_preserves_input_socket_even_for_the_same_source(self):
        geo = self.obj.createNode("geo", run_init_scripts=False)
        self.addCleanup(geo.destroy)
        source = geo.createNode("box", "SOURCE")
        subnet = geo.createNode("subnet", "SUB")
        geo.addSpareParmTuple(hou.RampParmTemplate("color_curve", "Tint", hou.rampParmType.Color))
        geo.parm("color_curve").set(
            hou.Ramp((hou.rampBasis.Linear,) * 2, (0.0, 1.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        )
        subnet.setInput(0, source)
        subnet.setInput(1, source)
        inside = subnet.createNode("xform", "INSIDE")
        inside.setInput(0, subnet.indirectInputs()[0])
        saved = graph_read(geo.path(), depth=2, snapshot=True)
        self.assertEqual(saved["root"]["parameters"]["color_curve"]["value"]["values"][1], [0, 1, 0])
        self.assertEqual(diff(saved["snapshot"])["total_changed"], 0)
        inside.setInput(0, subnet.indirectInputs()[1])
        row = diff(saved["snapshot"])["changed"][0]
        self.assertEqual(row["relative"], "SUB/INSIDE")
        before, after = (row["inputs"][k][0] for k in ("before", "after"))
        self.assertEqual((before["subnet_input"], after["subnet_input"]), (0, 1))
        self.assertEqual((after["subnet"], after["source"]), ("SUB", "SOURCE"))

    def test_old_bundle_compares_topology_without_touching_current_scene(self):
        key = "5fb39ac6ed9c4977a73fd9a31f2b4c50"
        info = details(key)["details"]
        bundle_name = info["bundle"] + ".cpio"
        root = load_checkpoint(stored("bundles", bundle_name))
        self.addCleanup(root.destroy)
        hou.setFrame(24)
        before = sorted(n.path() for n in self.obj.allSubChildren())
        pristine = diff(key, root.path())
        self.assertEqual(
            [pristine[k] for k in ("total_changed", "total_added", "total_removed")], [0, 0, 0]
        )
        self.assertEqual(sorted(n.path() for n in self.obj.allSubChildren()), before)
        self.assertEqual(hou.frame(), 24)
        scatter = root.node("SCATTER")
        scatter.parm("seed").set(123)
        delta = diff(key, root.path())
        self.assertEqual(delta["total_changed"], 1)
        self.assertEqual(delta["changed"][0]["parameters"]["seed"]["after"]["value"], 123)
        bad = Path(self.library) / "bundles" / bundle_name
        bad.parent.mkdir()
        bad.write_bytes(b"wrong bundle")
        with self.assertRaisesRegex(ValueError, "checksum"):
            diff(key, root.path())


if __name__ == "__main__":
    unittest.main()
