"""Read actual blue-body faces, holes, shoulders and selected neighbors."""
import collections,math
from .rack_checks import bounds,inside,distance_segment,TOL
from .assembly_checks import separation


def projected_clearance(part,point):
    clearance=float('inf')
    for face in part['faces']:
        poly=[(part['points'][i][1],part['points'][i][2]) for i in face]
        if inside(point,poly):return 0.
        clearance=min(clearance,min(distance_segment(point,a,b) for a,b in zip(poly,poly[1:]+poly[:1])))
    return clearance


def end_loops(part,x):
    """Boundary cycles of actual end-cap polygons, not inferred hole positions."""
    edges=collections.Counter()
    for face in part['faces']:
        if any(abs(part['points'][i][0]-x)>TOL for i in face):continue
        for a,b in zip(face,face[1:]+face[:1]):edges[tuple(sorted((a,b)))]+=1
    graph={}
    for (a,b),count in edges.items():
        if count==1:graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    if not graph or any(len(v)!=2 for v in graph.values()):return []
    remaining=set(graph);loops=[]
    while remaining:
        start=min(remaining);current=start;previous=None;loop=[]
        while True:
            if current in loop:
                if current!=start:return []
                break
            loop.append(current);remaining.discard(current)
            candidates=graph[current]-({previous} if previous is not None else set())
            previous,current=current,min(candidates)
        loops.append([(part['points'][i][1],part['points'][i][2]) for i in loop])
    return loops


def measure(parts,p):
    by={v['name']:v for v in parts};issues=[];body=by.get('pipe3_gasket');measurements={}
    if not body:return dict(passed=False,issues=['Missing lobed blue body'],measurements={})
    d=p['diameter_3'];cy=.044+p['rise_3']+d/2;cz=p['spacing_23'];offset=p['joint_offset_3'];count=int(p['bolt_count'])
    edges=collections.Counter();volume=0.;minarea=float('inf')
    for f in body['faces']:
        for i,j in zip(f,f[1:]+f[:1]):edges[i,j]+=1
        a=body['points'][f[0]];area=0.
        for k in range(1,len(f)-1):
            b,c=(body['points'][f[i]] for i in (k,k+1));ab=[b[i]-a[i] for i in range(3)];ac=[c[i]-a[i] for i in range(3)]
            cross=[ab[(i+1)%3]*ac[(i+2)%3]-ab[(i+2)%3]*ac[(i+1)%3] for i in range(3)]
            area+=math.sqrt(sum(v*v for v in cross))/2
            volume+=sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6
        minarea=min(minarea,area)
    closed=all(v==1 and edges[j,i]==1 for (i,j),v in list(edges.items()))
    euler=len(body['points'])-len(edges)//2+len(body['faces'])
    if not closed or volume<=0 or minarea<1e-14 or euler!=-2*count:issues.append('Blue body topology/orientation/holes invalid')
    lo,hi=bounds(body)
    if abs(lo[0]-(offset-.044))>TOL or abs(hi[0]-(offset+.044))>TOL:issues.append('Blue body axial seating mismatch')
    if any(not math.isfinite(v) for q in body['points'] for v in q):issues.append('Nonfinite blue body')
    profiles=[]
    for x,scale in [(-.044,.75),(-.032,.75),(-.024,1),(.024,1),(.032,.75),(.044,.75)]:
        ring=[q for q in body['points'] if abs(q[0]-offset-x)<TOL]
        if not ring:issues.append('Missing blue shoulder station');continue
        peaks=[];valleys=[]
        for k in range(count):
            for angle,target,out in [(2*math.pi*k/count,d*(.60+p['blue_lobe_depth']*scale),peaks),((2*k+1)*math.pi/count,.60*d,valleys)]:
                candidates=[math.hypot(q[1]-cy,q[2]-cz) for q in ring if abs(math.atan2(math.sin(math.atan2(q[2]-cz,q[1]-cy)-angle),math.cos(math.atan2(q[2]-cz,q[1]-cy)-angle)))<1e-5]
                radius=max(candidates) if candidates else 0;out.append(radius)
                if abs(radius-target)>TOL:issues.append('Blue lobe/valley/shoulder profile mismatch');break
        profiles.append(dict(x=x,peak_radii=peaks,valley_radii=valleys))
    bore=projected_clearance(body,(cy,cz));steps=max(8,2*math.ceil(p['segments']/count/2));expected=(d/2-p['wall_3'])*math.cos(math.pi/(count*steps))
    if bore<expected-TOL:issues.append('Blue body axial bore obstructed/off axis')
    loops=end_loops(body,lo[0]);actual_holes=[]
    if loops:
        outer=max(range(len(loops)),key=lambda i:abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(loops[i],loops[i][1:]+loops[i][:1]))))
        actual_holes=[loop for i,loop in enumerate(loops) if i!=outer and not inside((cy,cz),loop)]
    if len(loops)!=count+2 or len(actual_holes)!=count:issues.append('Blue body end boundary loops invalid')
    holes=[]
    for i in range(count):
        bolt=by.get(f'pipe3_bolt_{i:02}_shaft')
        if not bolt:issues.append('Missing blue body bolt');continue
        bl,bh=bounds(bolt);y=(bl[1]+bh[1])/2;z=(bl[2]+bh[2])/2
        r=max(math.hypot(q[1]-y,q[2]-z) for q in bolt['points']);gap=projected_clearance(body,(y,z))-r;holes.append(gap)
        matched=[loop for loop in actual_holes if inside((y,z),loop)]
        if len(matched)!=1 or gap<=TOL or bl[0]>lo[0]+TOL or bh[0]<hi[0]-TOL:issues.append('Bolt intersects or fails to span blue body hole')
    neighbors=[v for v in parts if not v['name'].startswith('pipe3_') and not v['name'].startswith('rack_')] + [v for v in parts if v['kind'] in ('channel_web','channel_lip','clamp','clamp_washer','clamp_nut','seat','hanger')]
    gap=None
    if neighbors:
        distance,name=min((separation(bounds(body),bounds(v)),v['name']) for v in neighbors);gap=dict(aabb_separation_lower_bound=distance,neighbor=name)
        if distance<.01-TOL:issues.append('Blue body neighbor clearance below visual margin')
    measurements.update(closed=closed,signed_volume=volume,euler=euler,profiles=profiles,end_boundary_loops=len(loops),actual_bolt_holes=len(actual_holes),axial_bore_radius=bore,minimum_bolt_hole_clearance=min(holes) if holes else None,neighbor_clearance=gap)
    return dict(passed=not issues,issues=sorted(set(issues)),measurements=measurements,scope='One inferred blue visual body; selected mesh interfaces, not product or engineering validation')
