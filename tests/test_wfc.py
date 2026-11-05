import unittest

from hlab.wfc import Contradiction, solve
from examples.wfc.rules import facade_request, maze_metrics, maze_request


def tile(name, west, east):
    return dict(name=name, west=west, east=east, south="face", north="face", weight=1)


class TiledLayoutTest(unittest.TestCase):
    def test_sockets_propagate_across_lock(self):
        tiles = [tile("plain", "j", "j"), tile("left", "j", "pair"), tile("right", "pair", "j")]
        pins = [dict(x=1, y=0, allow=["left"])]
        edges = dict(west="j", east="j", south="face", north="face")
        for seed in range(10):
            args = (5, 1, tiles, seed, pins, edges)
            result = solve(*args)
            self.assertEqual(result, solve(*args))
            self.assertEqual(result["layout"][0][1:3], ["left", "right"])
        with self.assertRaises(Contradiction):
            solve(5, 1, tiles, 1, pins+[dict(x=2, y=0, allow=["plain"])], edges)

    def test_conflicting_pin_on_single_cell(self):
        tiles = [tile("A", "x", "x"), tile("B", "x", "x")]
        pins = [dict(x=0, y=0, allow=[n]) for n in ("A", "B")]
        with self.assertRaises(Contradiction):
            solve(1, 1, tiles, 1, pins)

    def test_vertical_socket_and_impossible_border(self):
        tiles = [dict(tile("door", "j", "j"), north="header"),
                 dict(tile("hood", "j", "j"), south="header")]
        p = [dict(x=0, y=0, allow=["door"])]
        self.assertEqual(solve(1, 2, tiles, 0, p)["layout"], [["door"], ["hood"]])
        with self.assertRaises(Contradiction):
            solve(1, 2, tiles, 0, p, {"west": "closed"})

    def test_globally_connected_socket_and_forced_cycle(self):
        closed = dict(name="closed", west="wall", east="wall", south="wall", north="wall", weight=1)
        opened = dict(name="open", west="way", east="way", south="way", north="way", weight=1)
        self.assertEqual(solve(2, 2, [closed], 4)["layout"], [["closed"]*2]*2)
        with self.assertRaisesRegex(Contradiction, "disconnected"):
            solve(2, 2, [closed], 4, connected_socket="way")
        self.assertEqual(solve(2, 2, [opened], 4, connected_socket="way")["layout"], [["open"]*2]*2)
        with self.assertRaisesRegex(Contradiction, "cycle"):
            solve(2, 2, [opened], 4, connected_socket="way", loop_free=True)

    def test_bridge_propagation_with_zero_decisions(self):
        tiles = [tile("passage", "p", "p"), tile("blocked", "wall", "wall")]
        for seed in range(4):
            result = solve(3, 1, tiles, seed, connected_socket="p", loop_free=True)
            self.assertEqual(result["layout"], [["passage"]*3])
            self.assertEqual(result["stats"]["decisions"], 0)

    def test_real_maze_backtracks_and_reproduces_connected_tree(self):
        for seed in (25, 4, 7):
            with self.subTest(seed=seed):
                request = maze_request(seed)
                result = solve(**request)
                self.assertEqual(result, solve(**request))
                self.assertGreater(result["stats"]["backtracks"], 0)
                measured = maze_metrics(result["layout"])
                self.assertEqual((measured["reachable"], measured["interior_edges"], measured["gates"]),
                                 (143, 142, 2))
                self.assertTrue(measured["route"])
        local = maze_request(4)
        local.pop("connected_socket")
        local.pop("loop_free")
        measured = maze_metrics(solve(**local)["layout"])
        self.assertEqual(measured["reachable"], 103)
        self.assertEqual(measured["route"], [])

    def test_facade_locked_bays_preserve_pair_across_boundary(self):
        baseline = solve(**facade_request(3))["layout"]
        revised = solve(**facade_request(99, lock_from=baseline))["layout"]
        self.assertEqual([row[:6] for row in revised], [row[:6] for row in baseline])
        self.assertNotEqual(revised, baseline)
        self.assertEqual(revised[1][5:7], ["PAIR_L", "PAIR_R"])
        for layout in (baseline, revised):
            self.assertEqual((layout[0][2], layout[1][2]), ("DOOR", "HOOD"))

    def test_published_size_and_tile_limits(self):
        basic = tile("A", "x", "x")
        self.assertEqual(len(solve(16, 16, [basic], 0)["layout"]), 16)
        for columns, rows in ((257, 1), (0, 1), (1, -1)):
            with self.subTest(columns=columns, rows=rows), self.assertRaisesRegex(ValueError, "1 to 256"):
                solve(columns, rows, [basic], 0)
        with self.assertRaisesRegex(ValueError, "1 to 64"):
            solve(1, 1, [dict(basic, name=str(i)) for i in range(65)], 0)
