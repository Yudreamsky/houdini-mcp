"""Pure contract tests; native Houdini acceptance lives in the evidence folder."""
import math
import unittest

from houdini_mcp_local import lookdev_rig as rig


class LookdevRigTests(unittest.TestCase):
    def test_defaults_and_no_shared_mutability(self):
        settings = rig.validate_settings(rig.default_settings())
        self.assertEqual(len(settings["lights"]), 3)
        self.assertEqual(len(settings["cameras"]), 3)
        settings["lights"]["key"]["size"][0] = 1
        self.assertEqual(rig.default_settings()["lights"]["key"]["size"][0], 3.4)

    def test_partial_change_preserves_other_lights_and_cameras(self):
        before = rig.default_settings()
        after = rig.merge_settings(before, {"lights": {"fill": {"intensity": 3}}})
        self.assertEqual(after["lights"]["key"], before["lights"]["key"])
        self.assertEqual(after["cameras"], before["cameras"])
        self.assertEqual(before["lights"]["fill"]["intensity"], 1)

    def test_nonfinite_negative_or_zero_values_rejected(self):
        for field, value in (("size", [0, 1]), ("intensity", -1), ("exposure", math.inf),
                             ("color", [1, float("nan"), 0]), ("position", [False, 1, 2]),
                             ("enabled", 1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                rig.merge_settings(rig.default_settings(), {"lights": {"key": {field: value}}})

    def test_unknown_fields_and_wrong_types_rejected(self):
        for patch in ([], 0, {"lights": []}, {"foo": {}}, {"lights": {"other": {}}},
                      {"lights": {"key": {"script": "x"}}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                rig.merge_settings(rig.default_settings(), patch)

    def test_degenerate_direction_and_up_rejected(self):
        for change in ({"position": [0, 0, 0], "target": [0, 0, 0]},
                       {"position": [0, 1, 0], "target": [0, 0, 0], "up": [0, 1, 0]}):
            with self.assertRaises(ValueError):
                rig.merge_settings(rig.default_settings(), {"lights": {"key": change}})

    def test_projected_long_axis_and_minus_z_direction(self):
        spec = rig.default_settings()["lights"]["key"]
        matrix = rig.orientation_matrix(spec, True)
        x, y, z = matrix[:3], matrix[4:7], matrix[8:11]
        expected = rig._unit([1-z[0]*z[0], -z[0]*z[1], -z[0]*z[2]])
        self.assertLess(max(abs(a-b) for a, b in zip(x, expected)), 1e-12)
        self.assertLess(abs(rig._dot(x, y)), 1e-12)
        self.assertLess(abs(rig._dot(y, z)), 1e-12)
        self.assertEqual(matrix[12:15], spec["position"])
        forward = rig._unit([a-b for a, b in zip(spec["target"], spec["position"])])
        self.assertGreater(rig._dot(forward, [-v for v in z]), .999999)

    def test_capture_up_preserved_but_new_pose_reorients(self):
        base = rig.default_settings()
        base["lights"]["fill"]["up"] = [0, 1, 0]
        change = rig.merge_settings(base, {"lights": {"fill": {"position": [1, 2, 3]}}})
        self.assertNotIn("up", change["lights"]["fill"])
        same = rig.merge_settings(base, {})
        self.assertEqual(same["lights"]["fill"]["up"], [0, 1, 0])

    def test_path_traversal_and_invalid_names_rejected(self):
        for name in ("../cam", "a/b", "", "a"*49, "a-b", 1):
            with self.assertRaises(ValueError):
                rig._path(name)

    def test_camera_resolution_and_lens(self):
        for change in ({"resolution": [100.5, 100]}, {"focal_mm": 0}, {"aperture_mm": 1000}):
            with self.assertRaises(ValueError):
                rig.merge_settings(rig.default_settings(), {"cameras": {"hero": change}})

    def test_restore_snapshot_rejects_injected_parameters(self):
        rig._validate_snapshot({"exists": False})
        for value in ({"exists": False, "values": {}}, {"exists": True, "values": {"evil": {}}},
                      {"exists": "false"}):
            with self.assertRaises(ValueError):
                rig._validate_snapshot(value)


if __name__ == "__main__":
    unittest.main()
