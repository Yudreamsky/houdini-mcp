import unittest

from hlab.animation_gap import check_range, measure_frames, summarize

try:
    import hou
except ImportError:
    hou = None


class GapTests(unittest.TestCase):
    def test_bounds_and_first_violation(self):
        # Endpoints equal to the requested limits pass.
        summary = summarize([(1, 0.0, None), (2, 2.0, None), (3, -1.0, None),
                             (4, 3.0, None), (5, None, "empty")], 0.0, 2.0)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["first_violation"], {"frame": 3, "gap": -1.0})
        self.assertEqual(summary["lowest"]["frame"], 3)
        self.assertEqual(summary["highest"]["frame"], 4)
        self.assertEqual(summary["violating_frames"], 2)
        self.assertEqual(summary["missing_frames"], 1)

    def test_missing_and_unconstrained(self):
        incomplete = summarize([(7, None, "empty"), (8, 0.0, None)], 0.0, None)
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["first_missing"], {"frame": 7, "reason": "empty"})
        observed = summarize([(7, 0.0, None)], None, None)
        self.assertEqual(observed["status"], "measured")

    def test_invalid_range_axis_and_limits(self):
        for args in [(2, 1, "x", None, None), (0, 4096, "y", None, None),
                     (0, 1, "w", None, None), (0, 1, "y", 1.0, 0.0),
                     (0, 1, "z", None, float("nan"))]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                check_range(*args)
        check_range(-1, 0, "z", 0.0, 0.0)

    @unittest.skipUnless(hou is not None and not hou.isUIAvailable(), "requires standalone hython")
    def test_packed_geometry_in_animated_rotated_hierarchy(self):
        root = hou.node("/obj").createNode("subnet", "gap_test")
        try:
            mount = root.createNode("subnet", "mount")
            mount.parm("ty").set(10)
            mount.parm("rz").set(90)
            upper = mount.createNode("geo", "upper")
            upper.parm("tx").setExpression("$F", hou.exprLanguage.Hscript)
            box = upper.createNode("box")
            box.parmTuple("size").set((4, 2, 2))
            packed = box.createOutputNode("pack")
            packed.setDisplayFlag(True)
            lower = root.createNode("geo", "lower")
            lower.createNode("box").setDisplayFlag(True)
            req = dict(upper=packed.path(), lower=lower.path(), start=1, end=3,
                       axis="y", minimum=9, maximum=None)
            result = measure_frames(req)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["violating_frames"], 1)
            self.assertEqual(result["first_violation"]["frame"], 1)
            self.assertAlmostEqual(result["lowest"]["gap"], 8.5, places=4)
            self.assertAlmostEqual(result["highest"]["gap"], 10.5, places=4)
        finally:
            root.destroy()
