import collections
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local.sample_geometry import build,validate


class SampleTests(unittest.TestCase):
    def test_constraints_reject_invalid_combination_before_building(self):
        for values in ({'wall':.03,'diameter':.10},{'length':1.2,'support_pitch':2},{'segments':25},{'diameter':float('nan')},{'bolt_count':7.5}):
            with self.assertRaises(ValueError): validate(values)

    def test_components_are_closed_nonzero_meshes(self):
        for values in ({},{'diameter':.5,'length':3.6,'bolt_count':12},{'diameter':.1,'wall':.002,'bolt_count':6}):
            sample=build(values)
            self.assertEqual(len({p['name'] for p in sample['parts']}),len(sample['parts']))
            for part in sample['parts']:
                edges=collections.Counter(); directed=collections.Counter(); volume=0
                for face in part['faces']:
                    self.assertEqual(len(face),len(set(face)),part['name'])
                    for a,b in zip(face,face[1:]+face[:1]):
                        edges[tuple(sorted((a,b)))]+=1; directed[(a,b)]+=1
                    a=part['points'][face[0]]
                    for i in range(1,len(face)-1):
                        b,c=part['points'][face[i]],part['points'][face[i+1]]
                        volume+=sum(a[k]*(b[(k+1)%3]*c[(k+2)%3]-b[(k+2)%3]*c[(k+1)%3]) for k in range(3))/6
                self.assertTrue(all(n==2 for n in edges.values()),(values,part['name'],collections.Counter(edges.values())))
                self.assertTrue(all(directed[(b,a)]==n for (a,b),n in directed.items()),part['name'])
                self.assertGreater(volume,0,part['name'])

    def test_length_changes_support_coverage_and_preserves_existing_ids(self):
        a=build({});b=build({'length':3.6})
        self.assertEqual(len(a['support_positions']),2)
        self.assertEqual(len(b['support_positions']),4)
        self.assertLessEqual({v['name'] for v in a['parts']},{v['name'] for v in b['parts']})
        self.assertEqual(a['support_positions'],[-.45,.45])

    def test_real_bolt_holes_have_boundary_loops_on_flange_faces(self):
        sample=build({});flange=next(p for p in sample['parts'] if p['name']=='flange_left')
        # A closed flange with bore plus N through-holes has Euler characteristic -2N.
        edges={tuple(sorted((a,b))) for f in flange['faces'] for a,b in zip(f,f[1:]+f[:1])}
        self.assertEqual(len(flange['points'])-len(edges)+len(flange['faces']),-16)


if __name__=='__main__':unittest.main()
