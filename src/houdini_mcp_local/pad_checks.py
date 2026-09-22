"""Actual independent pad components, paired through holes, gaps and seating."""
import collections,math
from .rack_checks import bounds,inside,TOL
from .lobed_checks import end_loops,projected_clearance


def topology(part):
    edges=collections.Counter();graph={};volume=0.;minarea=float('inf')
    for f in part['faces']:
        for i,j in zip(f,f[1:]+f[:1]):
            edges[i,j]+=1;graph.setdefault(i,set()).add(j);graph.setdefault(j,set()).add(i)
        a=part['points'][f[0]];area=0.
        for k in range(1,len(f)-1):
            b,c=(part['points'][f[i]] for i in (k,k+1));ab=[b[i]-a[i] for i in range(3)];ac=[c[i]-a[i] for i in range(3)]
            cross=[ab[(i+1)%3]*ac[(i+2)%3]-ab[(i+2)%3]*ac[(i+1)%3] for i in range(3)]
            area+=math.sqrt(sum(v*v for v in cross))/2
            volume+=sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6
        minarea=min(minarea,area)
    remaining=set(graph);components=0
    while remaining:
        components+=1;stack=[remaining.pop()]
        while stack:
            linked=graph[stack.pop()]&remaining;remaining-=linked;stack.extend(linked)
    closed=bool(edges) and all(n==1 and edges[j,i]==1 for (i,j),n in list(edges.items()))
    return dict(closed=closed,components=components,euler=len(part['points'])-len(edges)//2+len(part['faces']),signed_volume=volume,minimum_face_area=minarea)


def measure(parts,p):
    by={v['name']:v for v in parts};issues=[];pads=[];disks=[];gaps=[]
    count=int(p['bolt_count']);d=p['diameter_3'];cy=.044+p['rise_3']+d/2;cz=p['spacing_23'];offset=p['joint_offset_3']
    names={f'pipe3_pad_{i:02}' for i in range(count)}
    actual={v['name'] for v in parts if v['kind']=='rubber_pad' or v['name'].startswith('pipe3_pad_')}
    if actual!=names or len(actual)!=sum(v['name'] in actual for v in parts):issues.append('Expected one uniquely named rubber pad per bolt')
    if 'pipe3_gasket' in by:issues.append('Rejected continuous blue body remains at first joint')
    for i in range(count):
        name=f'pipe3_pad_{i:02}';part=by.get(name);bolt=by.get(f'pipe3_bolt_{i:02}_shaft')
        if part is None or bolt is None:issues.append('Missing paired pad/bolt: '+name);continue
        if part['kind']!='rubber_pad':issues.append('Incorrect pad material identity: '+name)
        t=topology(part)
        if not t['closed'] or t['components']!=1 or t['euler']!=0 or t['signed_volume']<=0 or t['minimum_face_area']<1e-14:issues.append('Pad topology invalid: '+name)
        lo,hi=bounds(part);bl,bh=bounds(bolt);y=(lo[1]+hi[1])/2;z=(lo[2]+hi[2])/2
        byy=(bl[1]+bh[1])/2;bzz=(bl[2]+bh[2])/2;angle=2*math.pi*i/count
        r=max(math.hypot(q[1]-y,q[2]-z) for q in part['points']);disks.append((name,y,z,r))
        errors=[lo[0]-offset+.044,hi[0]-offset-.044,y-byy,z-bzz,y-cy-.635*d*math.cos(angle),z-cz-.635*d*math.sin(angle),r-p['pad_radius_ratio']*d]
        for fname,px in [('pipe3_flange_left',lo[0]),('pipe3_flange_right',hi[0])]:
            if fname not in by:issues.append('Missing pad contact flange');continue
            f=bounds(by[fname]);errors.append(px-f[1 if fname.endswith('left') else 0][0])
        if any(abs(v)>TOL for v in errors):issues.append('Pad axis/profile/contact mismatch: '+name)
        br=max(math.hypot(q[1]-byy,q[2]-bzz) for q in bolt['points'])
        clearance=projected_clearance(part,(byy,bzz))-br
        loopcounts=[]
        for x in (lo[0],hi[0]):
            loops=end_loops(part,x);loopcounts.append(len(loops))
            if len(loops)!=2:issues.append('Pad must have one actual through hole: '+name);continue
            inner=min(loops,key=lambda v:abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(v,v[1:]+v[:1]))))
            if not inside((byy,bzz),inner):issues.append('Bolt outside actual pad hole: '+name)
        if clearance<=TOL or bl[0]>lo[0]+TOL or bh[0]<hi[0]-TOL:issues.append('Bolt obstructed or does not span pad: '+name)
        bore=projected_clearance(part,(cy,cz))
        if bore<d/2-p['wall_3']+.005*d-TOL:issues.append('Pad intrudes into central bore: '+name)
        if any(not math.isfinite(v) for q in part['points'] for v in q):issues.append('Nonfinite pad')
        pads.append(dict(name=name,bolt=bolt['name'],topology=t,contact_axis_errors=errors,end_boundary_loops=loopcounts,bolt_hole_clearance=clearance,projected_pipe_bore_clearance=bore-(d/2-p['wall_3'])))
    for i,a in enumerate(disks):
        for b in disks[i+1:]:
            gap=math.hypot(a[1]-b[1],a[2]-b[2])-a[3]-b[3];gaps.append(gap)
            if gap<.012*d-TOL:issues.append('Independent pads touch or lack visual gap: '+a[0]+'/'+b[0])
    return dict(passed=not issues,issues=sorted(set(issues)),measurements=dict(pads=pads,pad_count=len(pads),minimum_pad_gap_lower_bound=min(gaps) if gaps else None,minimum_bolt_hole_clearance=min((v['bolt_hole_clearance'] for v in pads),default=None),internal_flow_connection='unmodeled'),scope='One independent buffer per existing bolt; actual mesh holes/contact and conservative disk gaps, not sealing or vibration performance')
