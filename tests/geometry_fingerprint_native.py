"""Run in hython: hython -m unittest tests.geometry_fingerprint_native. The geometry fingerprint of live studies reads
plain polygon geometry directly, changes with every kind of edit, leaves special geometry to the whole serialisation,
and is far quicker on a million points."""
import time
import unittest

import hou

from hlab.live_study import _direct_fingerprint, _fingerprint, _metrics, _serialized_fingerprint

POINTS, PRIMS, VERTICES, DETAIL = 2, 1, 3, 0


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.geo = hou.node("/obj").createNode("geo", run_init_scripts=False)
        self.addCleanup(self.geo.destroy)
        self.grid = self.geo.createNode("grid")
        self.grid.setParms({"rows": 5, "cols": 5})

    def after(self, kind, **parms):
        node = self.grid.createOutputNode(kind)
        node.setParms(parms)
        return node.geometry()

    def wrangle(self, cls, snippet):
        return self.after("attribwrangle", **{"class": cls, "snippet": snippet})

    def test_plain_polygons_are_read_directly_and_every_kind_of_edit_shows(self):
        base, scope = _fingerprint(self.grid.geometry())
        self.assertEqual(scope, "attributes")
        self.assertEqual(_fingerprint(self.grid.geometry())[0], base)  # the same geometry, the same hash
        self.assertEqual(_metrics(self.grid)["geometry_scope"], "attributes")
        edits = {
            "a point moved": self.wrangle(POINTS, "if (@ptnum == 7) @P.y += 0.001;"),
            "a point attribute": self.wrangle(POINTS, "f@heat = @ptnum;"),
            "another value in it": self.wrangle(POINTS, "f@heat = @ptnum * 2;"),
            "a primitive text attribute": self.wrangle(PRIMS, 's@name = "a";'),
            "another text in it": self.wrangle(PRIMS, 's@name = @primnum == 3 ? "b" : "a";'),
            "a vertex attribute": self.wrangle(VERTICES, "v@uv = set(@vtxnum, 0, 0);"),
            "a detail attribute": self.wrangle(DETAIL, "i@count = 3;"),
            "another detail value": self.wrangle(DETAIL, "i@count = 4;"),
            "faces reversed": self.after("reverse"),
            "only the last face reversed": self.after("reverse", group="15"),
            "faces opened": self.after("ends", closeu="open"),
            "a face removed": self.after("blast", group="3"),
            "points reordered": self.after("sort", ptsort="rev"),
        }
        seen = {"untouched": base}
        for label, geometry in edits.items():
            with self.subTest(edit=label):
                value, scope = _fingerprint(geometry)
                self.assertEqual(scope, "attributes")
                self.assertNotIn(value, seen.values(), f"{label} hashes like {[k for k, v in seen.items() if v == value]}")
                seen[label] = value

    def test_special_geometry_is_serialised_whole(self):
        special = {
            "a group": self.after("groupcreate", groupname="half", basegroup="0-5"),
            "a packed primitive": self.after("pack"),
            "an array attribute": self.wrangle(POINTS, "i[]@pair = array(@ptnum, 1);"),
            "a primitive that is not a polygon": self.after("convert", totype="mesh"),
        }
        for label, geometry in special.items():
            with self.subTest(geometry=label):
                value, scope = _fingerprint(geometry)
                self.assertEqual(scope, "serialized")
                self.assertEqual(_fingerprint(geometry)[0], value)
        a, _ = _fingerprint(self.after("groupcreate", groupname="half", basegroup="0-5"))
        b, _ = _fingerprint(self.after("groupcreate", groupname="half", basegroup="0-6"))
        self.assertNotEqual(a, b)  # membership of a group is only in the serialisation

    def test_a_million_points_take_a_fraction_of_the_serialisation(self):
        self.grid.setParms({"rows": 1000, "cols": 1000})
        # Like a scattered scene: colour, a normal, two numbers and a name on every point.
        geometry = self.wrangle(POINTS, 'v@Cd = set(@ptnum % 7, 0.5, 1); v@N = set(0, 1, 0); f@heat = @ptnum; '
                                        'i@piece = @ptnum / 9; s@kind = @ptnum % 2 ? "leaf" : "bark";')
        self.assertEqual(geometry.intrinsicValue("pointcount"), 1000000)
        started = time.perf_counter()
        direct = _direct_fingerprint(geometry)
        quick = time.perf_counter() - started
        started = time.perf_counter()
        _serialized_fingerprint(geometry)
        slow = time.perf_counter() - started
        self.assertEqual(_fingerprint(geometry), (direct, "attributes"))
        self.assertLess(quick, 3)
        self.assertLess(quick * 2, slow)
        print(f" 1,000,000 points: direct {quick:.2f} s, serialised {slow:.2f} s")


if __name__ == "__main__":
    unittest.main()
