import math
import unittest

from hlab.mechanism_math import check_fourbar_sweep, four_points, rope_path


class MechanismTest(unittest.TestCase):
    def test_unreachable_position_between_valid_keys(self):
        spec = dict(ground_a=(0, 0), ground_d=(3, 0), crank=1, coupler=2, rocker=1.5,
                    keys=[(1, 90), (2, 270)], branch="left")
        for angle in (90, 270):
            four_points((0, 0), (3, 0), 1, 2, 1.5, angle, "left")
        with self.assertRaisesRegex(ValueError, "cannot close"):
            check_fourbar_sweep(spec)

    def test_open_and_crossed_assembly(self):
        for branch, sign in [("left", 1), ("right", -1)]:
            a, b, c, d = four_points((0, 0), (3, 0), 1, 2.4, 2, 35, branch)
            cross = (d[0]-b[0])*(c[1]-b[1]) - (d[1]-b[1])*(c[0]-b[0])
            self.assertGreater(sign*cross, 0)
            for p, q, length in [(a, b, 1), (b, c, 2.4), (d, c, 2)]:
                self.assertAlmostEqual(math.dist(p, q), length)

    def test_variable_rope_length_and_travel_limit(self):
        for falls in (2, 4):
            before = rope_path(falls, .18, 12)
            after = rope_path(falls, .18, 12 - 2/falls)
            def length(points):
                return sum(math.dist(p, q) for p, q in zip(points, points[1:]))
            self.assertAlmostEqual(length(before)-length(after), 2)
        with self.assertRaisesRegex(ValueError, "separation"):
            rope_path(2, .18, .35)
