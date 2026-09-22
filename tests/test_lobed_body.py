import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import lobed_rack_geometry as g,repeated_rack_geometry as old,lobed_checks as ck

class LobedBodyTests(unittest.TestCase):
    def test_only_one_body_changes(self):
        a={v['name']:v for v in old.build({})['parts']};s=g.build({});b={v['name']:v for v in s['parts']}
        self.assertEqual(set(a),set(b));self.assertEqual([n for n in a if a[n]!=b[n]],['pipe3_gasket'])
        r=ck.measure(s['parts'],s['parameters']);self.assertTrue(r['passed'],r['issues']);self.assertEqual(r['measurements']['euler'],-16)

    def test_diameter_count_and_depth_matrix(self):
        for d,count,depth in [(.10,6,.12),(.28,8,.20),(.60,16,.22),(.28,7,.22)]:
            s=g.build(dict(diameter_3=d,bolt_count=count,blue_lobe_depth=depth,spacing_23=1.0,hanger_height=1.4))
            r=ck.measure(s['parts'],s['parameters']);self.assertTrue(r['passed'],(d,count,depth,r['issues']))
            self.assertGreater(r['measurements']['minimum_bolt_hole_clearance'],0)

    def test_shifted_rotated_body_and_blocked_bore(self):
        import math
        s=g.build({});p=s['parameters'];cy=.044+p['diameter_3']/2;cz=p['spacing_23']
        for action in ('shift','rotate','block'):
            parts=copy.deepcopy(s['parts']);body=next(v for v in parts if v['name']=='pipe3_gasket')
            if action=='block':
                n=len(body['points']);body['points'].extend([(p['joint_offset_3'],cy+y,cz+z) for y,z in [(-.04,-.04),(.04,-.04),(.04,.04),(-.04,.04)]]);body['faces'].append(list(range(n,n+4)))
            else:
                for q in body['points']:
                    if action=='shift':q[0]+=.02
                    else:
                        a=math.pi/p['bolt_count'];y=q[1]-cy;z=q[2]-cz;q[1]=cy+y*math.cos(a)-z*math.sin(a);q[2]=cz+y*math.sin(a)+z*math.cos(a)
            result=ck.measure(parts,p);self.assertFalse(result['passed'],action)
            if action=='block':self.assertIn('Blue body axial bore obstructed/off axis',result['issues'])
            if action=='rotate':self.assertIn('Bolt intersects or fails to span blue body hole',result['issues'])

    def test_depth_adjustment_preserves_neighbors(self):
        a=g.build({});b=g.build({'blue_lobe_depth':.12})
        self.assertEqual([v for v in a['parts'] if v['name']!='pipe3_gasket'],[v for v in b['parts'] if v['name']!='pipe3_gasket'])
        self.assertTrue(ck.measure(b['parts'],b['parameters'])['passed'])

    def test_invalid_envelope_and_depth_rejected(self):
        for p in ({'blue_lobe_depth':True},{'blue_lobe_depth':.3},{'diameter_3':.6,'spacing_23':.73}):
            with self.assertRaises(ValueError):g.validate(p)

if __name__=='__main__':unittest.main()
