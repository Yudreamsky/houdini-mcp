"""Independent topology, dimensions and material-volume checks for the S1 study."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import slotted_channel_sample as sample
from houdini_mcp_local.pad_checks import topology


class ChannelTests(unittest.TestCase):
    def check_shape(self,values):
        d=sample.build(values);p=d['parameters'];t=topology(d);n=len(d['slot_centers'])
        self.assertTrue(t['closed']);self.assertEqual(t['components'],1)
        self.assertEqual(t['euler'],2-2*n);self.assertGreater(t['minimum_face_area'],1e-12)
        for axis,expected in enumerate((p['width'],p['depth'],p['length'])):
            self.assertAlmostEqual(max(q[axis] for q in d['points'])-min(q[axis] for q in d['points']),expected,places=8)
        # Independent approximate section volume (minus two outside tiny chamfers),
        # less analytical capsule-hole volume; finite hole tessellation adds <0.2%.
        w,h,twall,lip=(p[k] for k in ('width','depth','thickness','lip'))
        section=w*twall+2*(h-twall)*twall+2*(lip-twall)*twall-.18*twall*twall
        hole=(p['slot_length']-p['slot_width'])*p['slot_width']+math.pi*(p['slot_width']/2)**2
        expected=section*p['length']-n*hole*twall
        self.assertLess(abs(t['signed_volume']-expected)/expected,.002)
        return d

    def test_default_and_growth(self):
        for v in ({},{'length':1.47,'width':.052,'depth':.05,'thickness':.003,'lip':.010,'pitch':.075,'slot_length':.031,'slot_width':.014}, {'length':.3}, {'pitch':.09}):
            with self.subTest(v=v):self.check_shape(v)

    def test_invalid_combinations(self):
        for v in ({'lip':.020},{'thickness':.006},{'slot_width':.04},{'slot_length':.059},{'pitch':.8},{'width':float('nan')},{'length':True},{'bogus':1}):
            with self.subTest(v=v),self.assertRaises(ValueError):sample.build(v)

    def test_missing_face_detected(self):
        d=sample.build();d['faces'].pop();self.assertFalse(topology(d)['closed'])

    def test_slot_not_ellipse(self):
        d=sample.build();p=d['parameters'];z=d['slot_centers'][len(d['slot_centers'])//2]
        # Straight parallel slot edges survive for the central portion.
        straight=[q for q in d['points'] if abs(q[1]-p['depth'])<1e-9 and abs(abs(q[0])-p['slot_width']/2)<1e-8 and abs(q[2]-z)<(p['slot_length']-p['slot_width'])/2]
        self.assertGreaterEqual(len(straight),4)


if __name__=='__main__':unittest.main()
