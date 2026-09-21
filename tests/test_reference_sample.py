import collections
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import reference_geometry as g,rack_checks


class ReferenceTests(unittest.TestCase):
    def test_reference_defaults_and_closed_folded_parts(self):
        s=g.build({});self.assertEqual(len(s['parts']),187)
        self.assertFalse(any(p['kind']=='seat' for p in s['parts']))
        check=rack_checks.measure(s['parts'],s['parameters'],folded=True);self.assertTrue(check['passed'],check['issues'])
        for p in s['parts']:
            directed=collections.Counter();volume=0
            for f in p['faces']:
                for a,b in zip(f,f[1:]+f[:1]):directed[(a,b)]+=1
                a=p['points'][f[0]]
                for j in range(1,len(f)-1):
                    b,c=p['points'][f[j]],p['points'][f[j+1]]
                    volume+=sum(a[k]*(b[(k+1)%3]*c[(k+2)%3]-b[(k+2)%3]*c[(k+1)%3]) for k in range(3))/6
            self.assertTrue(all(v==1 and directed[(b,a)]==v for (a,b),v in directed.items()),p['name'])
            self.assertGreater(volume,0,p['name'])
        sides=[p for p in s['parts'] if p['kind']=='channel_lip']
        self.assertTrue(all(len(p['points'])==16 for p in sides))

    def test_joint_offset_changes_interfaces_without_moving_pipe_ends(self):
        s=g.build({'joint_offset_2':.18});p=s['parameters'];by={v['name']:v for v in s['parts']}
        body=rack_checks.bounds(by['pipe2_gasket']);left=rack_checks.bounds(by['pipe2_pipe_left']);right=rack_checks.bounds(by['pipe2_pipe_right'])
        self.assertAlmostEqual(body[1][0]-body[0][0],.088)
        self.assertAlmostEqual(left[0][0],-p['length']/2);self.assertAlmostEqual(right[1][0],p['length']/2)
        self.assertAlmostEqual(left[1][0],body[0][0]);self.assertAlmostEqual(right[0][0],body[1][0])
        self.assertNotEqual(by['pipe2_flange_left']['color'],by['pipe2_gasket']['color'])

    def test_joint_support_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError,'overlaps a support'):
            g.validate({'support_pitch':.4,'joint_offset_2':.20})


if __name__=='__main__':unittest.main()
