import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import isolated_rack_geometry as g,repeated_rack_geometry as old,pad_checks as ck

class IsolationPadTests(unittest.TestCase):
    def test_exact_replacement(self):
        a={v['name']:v for v in old.build({})['parts']};s=g.build({});b={v['name']:v for v in s['parts']}
        self.assertEqual(set(a)-set(b),{'pipe3_gasket'});self.assertEqual(len(set(b)-set(a)),8)
        self.assertEqual(len(b),212);self.assertTrue(all(a[n]==b[n] for n in set(a)&set(b)))
        r=ck.measure(s['parts'],s['parameters']);self.assertTrue(r['passed'],r['issues'])
        self.assertEqual(r['measurements']['internal_flow_connection'],'unmodeled')

    def test_count_diameter_and_radius(self):
        for d,count,r in [(.10,6,.14),(.28,8,.14),(.60,16,.10),(.28,7,.12),(.28,8,.06)]:
            s=g.build(dict(diameter_3=d,bolt_count=count,pad_radius_ratio=r,spacing_23=1.,hanger_height=1.4))
            result=ck.measure(s['parts'],s['parameters']);self.assertTrue(result['passed'],(d,count,r,result['issues']))

    def test_invalid_combinations(self):
        for p in ({'pad_radius_ratio':True},{'pad_radius_ratio':float('nan')},{'pad_radius_ratio':.17},{'bolt_count':16},{'diameter_3':.60,'spacing_23':1.,'pad_radius_ratio':.16},{'blue_lobe_depth':.2}):
            with self.assertRaises(ValueError,msg=str(p)):g.build(p)

    def test_local_radius_edit(self):
        a=g.build({});b=g.build({'pad_radius_ratio':.12})
        self.assertEqual([v for v in a['parts'] if v['kind']!='rubber_pad'],[v for v in b['parts'] if v['kind']!='rubber_pad'])
        self.assertTrue(ck.measure(b['parts'],b['parameters'])['passed'])

    def test_missing_misaligned_blocked_and_continuous(self):
        s=g.build({})
        for action in ('missing','axial_gap','axis','blocked','continuous','disconnected'):
            parts=copy.deepcopy(s['parts']);part=next(v for v in parts if v['name']=='pipe3_pad_00')
            if action=='missing':parts.remove(part)
            elif action=='continuous':parts.append(next(v for v in old.build({})['parts'] if v['name']=='pipe3_gasket'))
            elif action in ('axial_gap','axis'):
                for q in part['points']:q[0 if action=='axial_gap' else 1]+=.02
            elif action=='disconnected':
                extra=copy.deepcopy(part);n=len(part['points']);part['points']+=extra['points'];part['faces']+=[[i+n for i in f] for f in extra['faces']]
            else:
                cy=.044+s['parameters']['diameter_3']/2+.635*s['parameters']['diameter_3'];cz=s['parameters']['spacing_23'];n=len(part['points'])
                part['points'] += [[.12,cy+y,cz+z] for y,z in [(-.02,-.02),(.02,-.02),(.02,.02),(-.02,.02)]];part['faces'].append(list(range(n,n+4)))
            result=ck.measure(parts,s['parameters']);self.assertFalse(result['passed'],action)

if __name__=='__main__':unittest.main()
