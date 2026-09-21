import collections
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local.elbow_geometry import build,validate


class ElbowTests(unittest.TestCase):
    def test_combined_constraints(self):
        for p in ({'diameter':.6,'bend_radius':.6},{'outlet_length':1.2,'support_pitch':1.1},
                  {'bend_segments':8.5},{'bend_radius':float('nan')},{'length':3}):
            with self.assertRaises(ValueError):validate(p)

    def test_elbow_winding_closed_volume_and_end_rings(self):
        for p in ({},{'diameter':.6,'bend_radius':.9,'wall':.03,'bend_segments':8},
                  {'diameter':.1,'bend_radius':.2,'wall':.002,'segments':24}):
            sample=build(p);parts={v['name']:v for v in sample['parts']};e=parts['elbow']
            edges=collections.Counter();directed=collections.Counter();volume=0
            for f in e['faces']:
                for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))]+=1;directed[(a,b)]+=1
                a=e['points'][f[0]]
                for i in range(1,len(f)-1):
                    b,c=e['points'][f[i]],e['points'][f[i+1]]
                    volume+=sum(a[k]*(b[(k+1)%3]*c[(k+2)%3]-b[(k+2)%3]*c[(k+1)%3]) for k in range(3))/6
            self.assertTrue(all(n==2 for n in edges.values()))
            self.assertTrue(all(directed[(b,a)]==n for (a,b),n in directed.items()))
            self.assertGreater(volume,0)
            for name,axis,high,elbow_high in [('inlet_pipe_right',0,True,False),('outlet_pipe_left',2,False,True)]:
                def ring(part,maximum):
                    points=part['points'];end=(max if maximum else min)(v[axis] for v in points)
                    return {tuple(round(x,8) for x in v) for v in points if abs(v[axis]-end)<1e-8}
                self.assertEqual(ring(parts[name],high),ring(e,elbow_high))

    def test_lengths_update_ports_and_support_identity(self):
        a=build({});b=build({'inlet_length':4.2,'outlet_length':3.6})
        self.assertLessEqual({v['name'] for v in a['parts']},{v['name'] for v in b['parts']})
        self.assertEqual(b['ports'][0]['center'][0],-4.2)
        self.assertAlmostEqual(b['ports'][1]['center'][2],4.2)
        self.assertEqual(sum(len(v) for v in a['support_positions'].values()),4)
        self.assertEqual(sum(len(v) for v in b['support_positions'].values()),8)

if __name__=='__main__':unittest.main()
