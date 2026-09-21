"""Bounded AABB separation and per-part fingerprints for local replacement review."""
import hashlib,json,math
from .rack_checks import bounds

def separation(a,b):
    return math.sqrt(sum(max(a[0][i]-b[1][i],b[0][i]-a[1][i],0)**2 for i in range(3)))

def coupling_clearances(parts,margin=.01):
    boxes={v['name']:bounds(v) for v in parts}
    selected=[v['name'] for v in parts if v['name'].startswith('pipe1_') and v['kind']!='pipe']
    groups={'u_bolts':[v['name'] for v in parts if v['kind'] in ('clamp','clamp_washer','clamp_nut')],
            'channels':[v['name'] for v in parts if v['kind'] in ('channel_web','channel_lip','seat')],
            'other_neighbors':[v['name'] for v in parts if not v['name'].startswith('pipe1_') and v['kind'] not in ('clamp','clamp_washer','clamp_nut','channel_web','channel_lip','seat')]}
    measurements={};issues=[]
    if not selected:return dict(passed=False,issues=['Missing red joint'],measurements={})
    for key,names in groups.items():
        if not names:issues.append('Missing neighbor group: '+key);continue
        distance,a,b=min((separation(boxes[a],boxes[b]),a,b) for a in selected for b in names)
        measurements[key]=dict(aabb_separation_lower_bound=distance,parts=[a,b],required_visual_margin=margin)
        if distance<margin-3e-6:issues.append('External joint clearance below margin: '+key)
    return dict(passed=not issues,issues=issues,measurements=measurements,
                scope='Conservative local AABB lower bounds; overlapping boxes are inconclusive, not proof of mesh collision; 10mm is a visual recipe margin')

def fingerprints(geo):
    """Native face positions/kind/Cd, independent of global point and primitive indices."""
    records={}
    for prim in geo.prims():
        name=prim.attribValue('name')
        records.setdefault(name,[]).append([prim.attribValue('part_type'),list(prim.attribValue('Cd')),[list(v.point().position()) for v in prim.vertices()]])
    return {name:hashlib.sha256(json.dumps(faces,separators=(',',':')).encode()).hexdigest() for name,faces in records.items()}

def compare(before,after):
    a=set(before);b=set(after)
    return dict(unchanged=sorted(n for n in a&b if before[n]==after[n]),changed=sorted(n for n in a&b if before[n]!=after[n]),removed=sorted(a-b),added=sorted(b-a))
