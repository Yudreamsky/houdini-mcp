import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import coupling_geometry as g,coupling_checks as ck,recipe_contract

class CouplingTests(unittest.TestCase):
    def test_default_manifold_bore_and_actual_holes(self):
        spec=g.build({});r=ck.measure(spec['parts'],spec['parameters'])
        self.assertTrue(r['passed'],r['issues']);self.assertEqual(len(spec['parts']),19)
        self.assertGreater(r['measurements']['minimum_lug_hole_clearance'],0)
        self.assertTrue(all(p['signed_volume']>0 for p in r['parts']))
    def test_three_geometric_negatives(self):
        spec=g.build({'clocking':0})
        for name,axis,message in [('pipe_right',1,'Pipe off axis'),('housing_upper',0,'Housing axial alignment'),('bolt_1',2,'Bolt misses')]:
            parts=copy.deepcopy(spec['parts'])
            for part in parts:
                if part['name']==name:
                    for q in part['points']:q[axis]+=.02
            r=ck.measure(parts,spec['parameters']);self.assertFalse(r['passed']);self.assertTrue(any(message in e for e in r['issues']),r['issues'])
    def test_parameter_matrix_and_rotated_hole_clearance(self):
        for d in (.1,.32,.6):
            for angle in (-180,-35,0,73,180):
                spec=g.build({'diameter':d,'clocking':angle,'joint_offset':.1})
                r=ck.measure(spec['parts'],spec['parameters']);self.assertTrue(r['passed'],(d,angle,r['issues']))
    def test_offset_contract_and_generator_agree(self):
        for length in (.4,.8):
            for offset in (-.2,0,.2):
                p={k:v[0] for k,v in g.PARAMETERS.items()};p.update(length=length,joint_offset=offset)
                errors=recipe_contract.violations('external_coupling_sample',g.PARAMETERS,p)
                try:g.validate(p);valid=True
                except ValueError:valid=False
                self.assertEqual(valid,not errors)
    def test_clocking_retains_pipe_mesh_and_part_names(self):
        a=g.build({'clocking':0});b=g.build({'clocking':73})
        self.assertEqual([p['name'] for p in a['parts']],[p['name'] for p in b['parts']])
        self.assertEqual(a['parts'][:2],b['parts'][:2])
    def test_shifted_seal_and_blocked_bore_are_rejected(self):
        spec=g.build({'clocking':0});parts=copy.deepcopy(spec['parts'])
        for part in parts:
            if part['kind']=='seal':
                for q in part['points']:q[0]+=.02
        self.assertIn('Seal axial alignment',ck.measure(parts,spec['parameters'])['issues'])
        for part in parts:
            if part['kind']=='seal':
                for q in part['points']:q[1]*=.8;q[2]*=.8
        self.assertIn('Axial flow bore obstructed or off axis',ck.measure(parts,spec['parameters'])['issues'])

if __name__=='__main__':unittest.main()
