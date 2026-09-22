"""Request boundary and evidence semantics, runnable without Houdini."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from houdini_mcp_local.render_diagnostics import (validate_diagnostics, configure_mantra,
                                                compare_pixels, LPE)


class DiagnosticsTests(unittest.TestCase):
    def test_disabled_default_does_not_touch_renderer(self):
        self.assertEqual(configure_mantra(object(), None), {})

    def test_accept_and_copy_request(self):
        request = {'aovs': list(LPE), 'denoise': True}
        result = validate_diagnostics(request)
        result['aovs'].clear()
        self.assertEqual(len(request['aovs']), 4)

    def test_reject_ambiguous_or_unsupported_request(self):
        invalid = [[], {'aovs': 'direct_diffuse'}, {'aovs': [False]},
                   {'aovs': ['arbitrary_source']}, {'aovs': ['direct_diffuse'] * 2},
                   {'denoise': 1}, {'denoise': 'false'}, {'output': '../raw.exr'}]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                validate_diagnostics(request)

    def test_comparison_is_not_quality_acceptance(self):
        before = [[0, 0, 0], [1, 1, 1], [0, 0, 0], [1, 1, 1]]
        after = [[.5, .5, .5]] * 4
        result = compare_pixels(before, after, 2, 2)
        self.assertAlmostEqual(result['gradient_retention_ratio'], 0)
        self.assertAlmostEqual(result['mean_absolute_rgb_difference'], .5)
        self.assertIn('not a quality score', result['note'])

    def test_nonfinite_or_wrong_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            compare_pixels([[float('nan')] * 3] * 4, [[0] * 3] * 4, 2, 2)
        with self.assertRaises(ValueError):
            compare_pixels([[0] * 3] * 3, [[0] * 3] * 3, 2, 2)


if __name__ == '__main__':
    unittest.main()
