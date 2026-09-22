import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import all_pads_geometry as g,isolated_rack_geometry as old,all_pad_checks as ck

class AllPadsTests(unittest.TestCase):
    def test_local_replacement(self):
        a={v['name']:v for v in old.build({})['parts']};s=g.build({});b={v['name']:v for v in s['parts']}
        self.assertEqual(set(a)-set(b),{'pipe2_gasket','pipe3_joint_b_gasket'})
        self.assertEqual(len(b),226);self.assertEqual(len(set(b)-set(a)),16);self.assertTrue(all(a[n]==b[n] for n in set(a)&set(b)))
        r=ck.measure(s['parts'],s['parameters']);self.assertTrue(r['passed'],r['issues']);self.assertEqual(r['pad_count'],24)

    def test_independent_axes_and_sizes(self):
        for values in ({'diameter_2':.4,'spacing_12':.75,'spacing_23':.75,'rise_2':.1}, {'diameter_3':.32,'spacing_23':.65,'second_joint_offset_3':1.02}, {'bolt_count':16,'pad_radius_ratio':.1}, {'bolt_count':6,'diameter_2':.1}):
            s=g.build(values);r=ck.measure(s['parts'],s['parameters']);self.assertTrue(r['passed'],r['issues'])

    def test_each_joint_bad_pad_or_bolt(self):
        s=g.build({})
        for prefix in ('pipe2_','pipe3_','pipe3_joint_b_'):
            for kind in ('pad_00','bolt_00_shaft'):
                parts=copy.deepcopy(s['parts']);v=next(v for v in parts if v['name']==prefix+kind)
                for q in v['points']:q[1]+=.02
                r=ck.measure(parts,s['parameters']);self.assertFalse(r['passed'],(prefix,kind))

    def test_missing_extra_and_legacy(self):
        s=g.build({})
        for prefix in ('pipe2_','pipe3_joint_b_'):
            parts=[v for v in s['parts'] if v['name']!=prefix+'pad_00'];self.assertFalse(ck.measure(parts,s['parameters'])['passed'])
            parts=s['parts']+[next(v for v in old.build({})['parts'] if v['name']==prefix+'gasket')]
            self.assertFalse(ck.measure(parts,s['parameters'])['passed'])
        extra=copy.deepcopy(next(v for v in s['parts'] if v['kind']=='rubber_pad'));extra['name']='unassigned_pad'
        self.assertFalse(ck.measure(s['parts']+[extra],s['parameters'])['passed'])

    def test_new_pipe2_constraints(self):
        for values in ({'diameter_2':.6,'pad_radius_ratio':.16,'spacing_12':1.,'spacing_23':1.}, {'spacing_23':.48}, {'bolt_count':16}):
            with self.assertRaises(ValueError):g.validate(values)

if __name__=='__main__':unittest.main()
