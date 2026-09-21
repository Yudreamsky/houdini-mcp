"""Inspect supplied meshes in the coupling's local frame; never regenerate them."""
import collections,math
from .rack_checks import bounds,hole_clearance,inside,distance_segment
TOL=3e-6

def measure(parts,p):
    issues=[];summaries=[];by={};a=math.radians(p['clocking']);c,s=math.cos(a),math.sin(a)
    for part in parts:
        q=dict(part);q['points']=[(x,y*c+z*s,-y*s+z*c) for x,y,z in part['points']];by[q['name']]=q
        edges=collections.Counter();volume=0.;minimum_area=float('inf')
        for f in q['faces']:
            for i,j in zip(f,f[1:]+f[:1]):edges[(i,j)]+=1
            v=q['points'][f[0]];area=0.
            for k in range(1,len(f)-1):
                b,t=q['points'][f[k]],q['points'][f[k+1]]
                volume+=sum(v[j]*(b[(j+1)%3]*t[(j+2)%3]-b[(j+2)%3]*t[(j+1)%3]) for j in range(3))/6
                ab=[b[j]-v[j] for j in range(3)];at=[t[j]-v[j] for j in range(3)]
                area+=math.sqrt(sum((ab[(j+1)%3]*at[(j+2)%3]-ab[(j+2)%3]*at[(j+1)%3])**2 for j in range(3)))/2
            minimum_area=min(minimum_area,area)
        closed=all(v==1 and edges[(j,i)]==1 for (i,j),v in list(edges.items()))
        if not closed or volume<=0 or minimum_area<1e-14 or any(not math.isfinite(v) for pt in q['points'] for v in pt):issues.append('Invalid mesh: '+q['name'])
        lo,hi=bounds(part);summaries.append(dict(name=q['name'],kind=q['kind'],bbox_min=lo,bbox_max=hi,points=len(q['points']),faces=len(q['faces']),closed_edges=closed,signed_volume=volume))
    required=['pipe_left','pipe_right','seal_envelope','housing_upper','housing_lower']
    for side in (-1,1):required += [f'{prefix}_{side}' for prefix in ('bolt','head','nut')]+[f'{prefix}_{side}_{half}' for prefix in ('lug','washer') for half in ('upper','lower')]
    if set(by)!=set(required):issues.append('Unexpected/missing coupling parts');return dict(passed=False,issues=issues,parts=summaries,measurements={})
    d=p['diameter'];r=d/2;o=p['joint_offset'];w=p['shell_width'];measurements={}
    def equal(actual,expected,message):
        if abs(actual-expected)>TOL:issues.append(message)
    for side in ('left','right'):
        part=by['pipe_'+side];lo,hi=bounds(part);equal((lo[1]+hi[1])/2,0,'Pipe off axis: '+side);equal((lo[2]+hi[2])/2,0,'Pipe off axis: '+side)
        radii=[math.hypot(v[1],v[2]) for v in part['points']]
        equal(max(radii),r,'Pipe outside radius: '+side);equal(min(radii),r-p['wall'],'Pipe bore radius: '+side)
        equal(lo[0],-p['length']/2 if side=='left' else o+.006*d,'Pipe start: '+side)
        equal(hi[0],o-.006*d if side=='left' else p['length']/2,'Pipe end: '+side)
    for half in ('upper','lower'):
        part=by['housing_'+half];lo,hi=bounds(part)
        equal(lo[0],o-w/2,'Housing axial alignment: '+half);equal(hi[0],o+w/2,'Housing axial alignment: '+half)
        rad=[math.hypot(q[1],q[2]) for q in part['points']]
        equal(min(rad),r+.006*d,'Housing radial alignment: '+half);equal(max(rad),r+.075*d,'Housing radial alignment: '+half)
        gap=(lo[1] if half=='upper' else -hi[1]);equal(gap,(r+.006*d)*math.sin(.012),'Housing split/clocking: '+half)
    seal=by['seal_envelope'];lo,hi=bounds(seal);rad=[math.hypot(q[1],q[2]) for q in seal['points']]
    equal(lo[0],o-.36*w,'Seal axial alignment');equal(hi[0],o+.36*w,'Seal axial alignment')
    equal(min(rad),r,'Seal radial alignment');equal(max(rad),r+.006*d,'Seal radial alignment')
    clearances=[]
    for side in (-1,1):
        rod=by[f'bolt_{side}'];lo,hi=bounds(rod);cx=(lo[0]+hi[0])/2;cz=(lo[2]+hi[2])/2
        equal(cx,o,'Bolt axial alignment');equal(cz,side*(r+.12*d),'Bolt lug alignment')
        rr=max(math.hypot(q[0]-cx,q[2]-cz) for q in rod['points'])
        equal(rr,.013*d,'Bolt radius');equal(lo[1],-.112*d,'Bolt span');equal(hi[1],.109*d,'Bolt span')
        for half,yl,yh in [('upper',.01*d,.0625*d),('lower',-.0625*d,-.01*d)]:
            lug=by[f'lug_{side}_{half}'];l,h=bounds(lug)
            equal((l[0]+h[0])/2,o,'Lug axial alignment');equal((l[2]+h[2])/2,side*(r+.12*d),'Lug radial alignment')
            equal(l[1],yl,'Lug split alignment');equal(h[1],yh,'Lug thickness')
            clearances.append(hole_clearance(lug,cx,cz,rr))
        for name,yl,yh in [(f'washer_{side}_upper',.0625*d,.075*d),(f'washer_{side}_lower',-.075*d,-.0625*d),(f'head_{side}',.075*d,.102*d),(f'nut_{side}',-.102*d,-.075*d)]:
            l,h=bounds(by[name]);equal(l[1],yl,'Hardware seating: '+name);equal(h[1],yh,'Hardware seating: '+name)
            equal((l[0]+h[0])/2,o,'Hardware axis: '+name);equal((l[2]+h[2])/2,side*(r+.12*d),'Hardware axis: '+name)
    if min(clearances)<=TOL:issues.append('Bolt misses or intersects actual lug hole')
    # Minimum radial distance to actual face projections tests an unobstructed axial bore.
    bore=float('inf')
    for part in by.values():
        for face in part['faces']:
            poly=[(part['points'][i][1],part['points'][i][2]) for i in face]
            if inside((0,0),poly):bore=0.;break
            bore=min(bore,min(distance_segment((0,0),u,v) for u,v in zip(poly,poly[1:]+poly[:1])))
    expected_bore=(r-p['wall'])*math.cos(math.pi/p['segments'])
    if bore<expected_bore-TOL:issues.append('Axial flow bore obstructed or off axis')
    measurements.update(minimum_lug_hole_clearance=min(clearances),axial_clear_radius=bore,expected_pipe_inscribed_radius=expected_bore,pipe_end_gap=bounds(by['pipe_right'])[0][0]-bounds(by['pipe_left'])[1][0])
    return dict(passed=not issues,issues=issues,parts=summaries,measurements=measurements)
