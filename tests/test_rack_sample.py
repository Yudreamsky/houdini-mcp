import collections
import copy
import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import rack_geometry as geometry,rack_checks,recipe_contract


class RackTests(unittest.TestCase):
    def test_closed_solids_shared_counts_and_dimension_changes(self):
        for values in ({},{'length':3.6,'diameter_1':.45,'spacing_12':.75,'rise_1':.06,'rise_2':0,'rise_3':.16},
                       {'diameter_1':.1,'diameter_2':.1,'diameter_3':.1,'spacing_12':.2,'spacing_23':.2,'rise_1':0,'rise_2':0,'rise_3':0}):
            sample=geometry.build(values);checked=rack_checks.measure(sample['parts'],sample['parameters'])
            self.assertTrue(checked['passed'],checked['issues'])
            count=len(sample['support_positions'])
            self.assertEqual(sum(p['kind']=='channel_web' for p in sample['parts']),count)
            self.assertEqual(sum(p['kind']=='hanger' for p in sample['parts']),2*count)
            self.assertEqual(sum(p['kind']=='clamp' for p in sample['parts']),3*count)
            for part in sample['parts']:
                edges=collections.Counter();directed=collections.Counter();volume=0
                for f in part['faces']:
                    for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))]+=1;directed[(a,b)]+=1
                    a=part['points'][f[0]]
                    for j in range(1,len(f)-1):
                        b,c=part['points'][f[j]],part['points'][f[j+1]]
                        volume+=sum(a[k]*(b[(k+1)%3]*c[(k+2)%3]-b[(k+2)%3]*c[(k+1)%3]) for k in range(3))/6
                self.assertTrue(all(v==2 for v in edges.values()),part['name'])
                self.assertTrue(all(directed[(b,a)]==n for (a,b),n in directed.items()),part['name'])
                self.assertGreater(volume,0,part['name'])

    def test_missing_seat_shifted_pipe_and_missed_hole_are_rejected(self):
        sample=geometry.build({});p=sample['parameters']
        parts=copy.deepcopy(sample['parts']);parts=[v for v in parts if v['name']!='rack_pos_0_pipe2_seat']
        self.assertFalse(rack_checks.measure(parts,p)['passed'])
        parts=copy.deepcopy(sample['parts'])
        for part in parts:
            if part['name'].startswith('pipe2_'):
                part['points']=[[x,y+.025,z-.45] for x,y,z in part['points']]
        check=rack_checks.measure(parts,p);self.assertFalse(check['passed'])
        self.assertTrue(any('clearance' in v for v in check['issues']))
        parts=copy.deepcopy(sample['parts'])
        for part in parts:
            if part['name']=='rack_pos_0_pipe2_clamp':part['points']=[[x+.012,y,z] for x,y,z in part['points']]
        check=rack_checks.measure(parts,p);self.assertTrue(any('real web opening' in v for v in check['issues']))

    def test_height_change_preserves_beam_and_support_identity(self):
        a=geometry.build({});b=geometry.build({'rise_2':.2});c=geometry.build({'length':3.6})
        webs=lambda s:[part for part in s['parts'] if part['kind']=='channel_web']
        self.assertEqual(webs(a),webs(b))
        self.assertLessEqual({v['name'] for v in a['parts']},{v['name'] for v in c['parts']})
        self.assertAlmostEqual(b['pipe_centers'][1][1]-a['pipe_centers'][1][1],.1)

    def test_contract_agrees_and_exposes_multiple_field_limits(self):
        for d,rise,spacing,h in itertools.product((.1,.32,.6),(0,.3),(.2,.6,1.2),(.7,1.2)):
            p={k:v[0] for k,v in geometry.PARAMETERS.items()};p.update(diameter_1=d,rise_1=rise,spacing_12=spacing,hanger_height=h)
            errors=recipe_contract.violations('pipe_rack_sample',geometry.PARAMETERS,p)
            try:geometry.validate(p);accepted=True
            except ValueError:accepted=False
            self.assertEqual(not errors,accepted,(p,errors))
        p={k:v[0] for k,v in geometry.PARAMETERS.items()};p.update(diameter_1=.6,rise_1=.3,hanger_height=.7,spacing_12=.2)
        errors=recipe_contract.violations('pipe_rack_sample',geometry.PARAMETERS,p)
        self.assertTrue(any(e['code']=='hanger_clearance_1' and 'rise_1' in e['fields'] for e in errors))
        self.assertTrue(any(e['code']=='flange_clearance_12' and 'diameter_2' in e['fields'] for e in errors))


if __name__=='__main__':unittest.main()
