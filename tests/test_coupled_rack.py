import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import coupled_rack_geometry as g,reference_geometry as ref,assembly_checks as ac,rack_checks

class CoupledRackTests(unittest.TestCase):
    def test_exact_preservation_and_default_clearance(self):
        old=ref.build({});new=g.build({});a={v['name']:v for v in old['parts']};b={v['name']:v for v in new['parts']}
        kept=[n for n in a if not n.startswith('pipe1_')];self.assertEqual(len(kept),142)
        self.assertEqual(len(b),161)
        for n in kept:self.assertEqual(a[n],b[n],n)
        self.assertEqual(new['replacement']['modified'],['pipe1_pipe_left','pipe1_pipe_right'])
        check=ac.coupling_clearances(new['parts']);self.assertTrue(check['passed'],check['issues'])
        names=[n for n in b if n.startswith('pipe1_') and b[n]['kind']!='pipe']
        self.assertTrue(rack_checks.measure(new['parts'],new['parameters'],folded=True,joint_parts={1:names})['passed'])
    def test_clocking_and_width_change_only_red_assembly(self):
        a=g.build({});b=g.build({'red_clocking':-70,'red_shell_width':.14})
        self.assertEqual([v for v in a['parts'] if not v['name'].startswith('pipe1_')],[v for v in b['parts'] if not v['name'].startswith('pipe1_')])
        for value in (a,b):self.assertTrue(ac.coupling_clearances(value['parts'])['passed'])
    def test_displaced_u_bolt_and_channel_clearance_fail(self):
        s=g.build({})
        for name,group in [('rack_pos_0_pipe1_clamp','u_bolts'),('rack_pos_0_web','channels')]:
            parts=copy.deepcopy(s['parts'])
            for p in parts:
                if p['name']==name:
                    for q in p['points']:q[0]-=.38
            result=ac.coupling_clearances(parts);self.assertFalse(result['passed']);self.assertTrue(any(group in v for v in result['issues']))
    def test_conservative_support_band_rejects_wide_shell(self):
        with self.assertRaisesRegex(ValueError,'clearance band'):
            g.validate({'diameter_1':.1,'support_pitch':.8,'joint_offset_1':.29,'red_shell_width':.16})

if __name__=='__main__':unittest.main()
