"""Portable refusal/mapping contract; real Houdini/USD evidence lives in evidence/."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('xpu_surface_test_module', Path(__file__).resolve().parents[1] / 'src/houdini_mcp_local/xpu_surface_adapter.py')
with patch.dict(sys.modules, {'hou': types.SimpleNamespace()}):
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

class Parm:
    def __init__(self, name, value): self.key, self.value = name, value
    def eval(self): return self.value
    def name(self): return self.key

class Material:
    def __init__(self, **overrides):
        self.values = dict(specmodel='ggx',opac=1,metallic=.8,reflect=.65,rough=.28,ior=1.5,basecolor_usePointColor=1,
                           basecolor=(.5,.53,.56),opaccolor=(1.,1.,1.))
        self.values.update(overrides)
    def type(self): return types.SimpleNamespace(name=lambda: 'principledshader::2.0')
    def inputs(self): return ()
    def path(self): return '/mat/test'
    def parms(self): return [Parm(k,v) for k,v in self.values.items()]
    def parm(self, key): return Parm(key,self.values[key]) if key in self.values else None
    parmTuple = parm

class PhysicalSurfaceContractTests(unittest.TestCase):
    def test_standard_surface_keeps_physical_parameters(self):
        mapped = adapter._material(Material())
        self.assertEqual(mapped['shader_id'], 'ND_standard_surface_surfaceshader')
        self.assertEqual(mapped['metalness'], .8)
        self.assertEqual(mapped['specular_roughness'], .28)
        self.assertTrue(mapped['use_Cd'])
    def test_active_unsupported_features_fail(self):
        for key in ('basecolor_useTexture','baseBumpAndNormal_enable','dispTex_enable','transparency','sss','coat','sheen','emitint','reflecttint'):
            with self.subTest(key=key), self.assertRaises(ValueError): adapter._material(Material(**{key:1}))
    def test_inactive_texture_filename_is_not_rejected(self):
        self.assertEqual(adapter._material(Material(basecolor_useTexture=0, basecolor_texture='unused.png'))['metalness'],.8)
    def test_invalid_numeric_and_nonopaque_materials_fail(self):
        for change in ({'rough':float('nan')},{'metallic':2},{'ior':1},{'opac':.5},{'opaccolor':(1.,1.,.5)}):
            with self.subTest(change=change), self.assertRaises(ValueError): adapter._material(Material(**change))
    def test_connected_material_is_not_silently_flattened(self):
        node=Material();node.inputs=lambda:(object(),)
        with self.assertRaises(ValueError): adapter._material(node)
    def test_path_contract_rejects_ambiguous_or_duplicate_scope(self):
        for value in ('/obj/key',['key'],['/obj/key','/obj/key'],[None]):
            with self.subTest(value=value), self.assertRaises(ValueError): adapter._paths({'light_paths':value},'light_paths')
        self.assertEqual(adapter._paths({'light_paths':['/obj/rig/key']},'light_paths'),{'/obj/rig/key'})
    def test_clockwise_face_matches_native_normal_numerically(self):
        report = adapter._orientation_audit([(0,0,0),(0,1,0),(1,0,0)], [3], [0,1,2], ([(0,0,1)]*3, 'faceVarying'))
        self.assertEqual(report['usd_orientation'], 'leftHanded')
        self.assertEqual(report['compared_faces'], 1)
        self.assertEqual(report['opposed_faces'], 0)
        self.assertAlmostEqual(report['minimum_dot'], 1.)
    def test_reversed_or_zero_authored_normals_are_refused(self):
        for normal in [(0,0,-1),(0,0,0)]:
            with self.subTest(normal=normal), self.assertRaises(ValueError):
                adapter._orientation_audit([(0,0,0),(0,1,0),(1,0,0)], [3], [0,1,2], ([normal]*3, 'faceVarying'))
    def test_nonzero_corner_normals_that_cancel_are_reported_not_called_zero_vectors(self):
        report = adapter._orientation_audit([(0,0,0),(0,1,0),(1,1,0),(1,0,0)], [4], [0,1,2,3],
                                            ([(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)], 'faceVarying'))
        self.assertEqual(report['zero_authored_vectors'], 0)
        self.assertEqual(report['cancelled_average_face_normals'], 1)
        self.assertEqual(report['compared_faces'], 0)
    def test_absent_normals_preserve_left_handed_generation(self):
        report = adapter._orientation_audit([(0,0,0),(0,1,0),(1,0,0)], [3], [0,1,2], None)
        self.assertIn('renderer generates', report['authored_normals'])
    def test_nonfinite_positions_are_rejected(self):
        with self.assertRaises(ValueError): adapter._finite([0,float('inf')],'position')

if __name__ == '__main__': unittest.main()
