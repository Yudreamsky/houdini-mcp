import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local.render_options import options, validate_region, region_ndc, extensions
from houdini_mcp_local.render_comparison import identity

class ControlsTests(unittest.TestCase):
    def test_sampling_rejects_ambiguous_or_nonfinite_values(self):
        for value in ({'pixel_samples':9}, {'pixel_samples':[True,4]}, {'min_rays':4},
                      {'min_rays':8,'max_rays':4}, {'noise_threshold':float('nan')},
                      {'noise_threshold':0}, {'sample_lock':1}, {'seed':-1}, {'unknown':1}):
            with self.subTest(value=value), self.assertRaises(ValueError): options('mantra','preview',value)
        self.assertEqual(options('mantra','preview',{'pixel_samples':[9,7]})['pixel_samples'],63)
        with self.assertRaises(ValueError): options('karma_xpu','preview',{'min_rays':1,'max_rays':4})
    def test_region_coordinates_and_bounds(self):
        self.assertEqual(region_ndc({'region':[20,10,60,30],'width':100,'height':50}),[.2,.4,.6,.8])
        for region in ([0,0,0,2],[-1,0,2,2],[0,0,101,50],[0,True,2,2],[0,0,1]):
            with self.assertRaises(ValueError): validate_region(region,100,50)
    def test_surface_extension_cannot_silently_select_wrong_backend(self):
        with self.assertRaises(ValueError): extensions('mantra',128,128,xpu_surface={})
        with self.assertRaises(ValueError): extensions('karma_xpu',128,128,xpu_surface={'light_paths':['relative']})
    def test_comparison_allows_sampling_only(self):
        base={'scene_sha256':'A','region':[0,0,128,128],'sampling':{'pixel_samples':[2,2],'seed':0}}
        self.assertEqual(identity(base),identity(dict(base,sampling={'pixel_samples':[8,8],'seed':0})))
        self.assertNotEqual(identity(base),identity(dict(base,scene_sha256='B')))
        self.assertNotEqual(identity(base),identity(dict(base,sampling={'pixel_samples':[8,8],'seed':1})))

if __name__=='__main__': unittest.main()
