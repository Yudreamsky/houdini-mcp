import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import repeated_rack_geometry as g,coupled_rack_geometry as old,repeated_checks as checks,recipe_contract


class RepeatedRackTests(unittest.TestCase):
    def test_saved_scope_and_three_span_chain(self):
        a={v['name']:v for v in old.build({})['parts']};s=g.build({});b={v['name']:v for v in s['parts']}
        self.assertEqual(len(b),205)
        self.assertEqual([n for n in a if a[n]!=b[n]],['pipe3_pipe_right'])
        self.assertEqual(len(set(b)-set(a)),44)
        result=checks.measure(s['parts'],s['parameters']);self.assertTrue(result['passed'],result)
        self.assertEqual({v['pipe_spans'][0] for v in result['measurements']['support_spans']},{'pipe3_pipe_left','pipe3_pipe_middle'})

    def test_move_second_joint_preserves_first_and_supports(self):
        a={v['name']:v for v in g.build({})['parts']};s=g.build({'second_joint_offset_3':1.1});b={v['name']:v for v in s['parts']}
        changed={n for n in a if a[n]!=b[n]}
        self.assertTrue(all(n.startswith('pipe3_joint_b_') or n in ('pipe3_pipe_middle','pipe3_pipe_right') for n in changed))
        self.assertTrue(checks.measure(s['parts'],s['parameters'])['passed'])

    def test_growth_covers_four_supports(self):
        s=g.build({'length':4.4,'diameter_3':.32,'spacing_23':.58,'second_joint_offset_3':1.1})
        check=checks.measure(s['parts'],s['parameters']);self.assertTrue(check['passed'],check)
        self.assertEqual(len(check['measurements']['support_spans']),4)

    def test_missing_or_shifted_middle_span_rejected(self):
        s=g.build({})
        for delta in (None,.02):
            parts=copy.deepcopy(s['parts'])
            if delta is None:parts=[v for v in parts if v['name']!='pipe3_pipe_middle']
            else:
                for v in parts:
                    if v['name']=='pipe3_pipe_middle':
                        for q in v['points']:q[0]+=delta
            self.assertFalse(checks.measure(parts,s['parameters'])['passed'])

    def test_parameter_rejection_and_contract(self):
        for values in ({'second_joint_offset_3':.6},{'second_joint_offset_3':1.35},{'second_joint_offset_3':.35,'joint_offset_3':.3}):
            with self.assertRaises(ValueError):g.validate(values)
        for key,value in [('second_joint_offset_3',float('nan')),('second_joint_offset_3',True),('second_joint_offset_3',[])]:
            with self.assertRaises(ValueError):g.validate({key:value})
        for b in (.35,.6,.98,1.35):
            p={k:v[0] for k,v in g.PARAMETERS.items()};p['second_joint_offset_3']=b
            errors=recipe_contract.violations('pipe_rack_repeated',g.PARAMETERS,p)
            if errors:
                with self.assertRaises(ValueError):g.validate(p)

    def test_shifted_joint_and_support_rejected(self):
        s=g.build({})
        for name,delta in [('pipe3_joint_b_gasket',.02),('rack_pos_0_web',.38)]:
            parts=copy.deepcopy(s['parts'])
            for v in parts:
                if v['name']==name:
                    for q in v['points']:q[0]+=delta
            self.assertFalse(checks.measure(parts,s['parameters'])['passed'])

if __name__=='__main__':unittest.main()
