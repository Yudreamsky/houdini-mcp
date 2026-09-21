"""Measure extracted mesh parts, never build expected geometry to claim a pass."""
import math

TOL=3e-6


def bounds(part):
    q=part['points']
    return ([min(v[a] for v in q) for a in range(3)],[max(v[a] for v in q) for a in range(3)])


def center(part):
    lo,hi=bounds(part);return [(a+b)/2 for a,b in zip(lo,hi)]


def distance_segment(q,a,b):
    ab=[b[i]-a[i] for i in range(2)];length=sum(v*v for v in ab)
    t=max(0,min(1,sum((q[i]-a[i])*ab[i] for i in range(2))/length)) if length else 0
    return math.dist(q,[a[i]+t*ab[i] for i in range(2)])


def inside(q,polygon):
    hit=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>q[1])!=(b[1]>q[1]) and q[0]<(b[0]-a[0])*(q[1]-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


def hole_clearance(web,cx,cz,radius):
    """Point must be inside web outline but outside every top polygon.

    Distance to polygon edges bounds the rod's circular cross-section clearance.
    This checks the actual polygonal hole, not only nearest mesh vertices.
    """
    lo,hi=bounds(web);q=(cx,cz)
    if not (lo[0]+radius<cx<hi[0]-radius and lo[2]+radius<cz<hi[2]-radius):return -1
    minimum=float('inf');found=False
    for face in web['faces']:
        pts=[web['points'][i] for i in face]
        if any(abs(v[1]-hi[1])>TOL for v in pts):continue
        found=True;poly=[(v[0],v[2]) for v in pts]
        if inside(q,poly):return -1
        minimum=min(minimum,min(distance_segment(q,a,b) for a,b in zip(poly,poly[1:]+poly[:1])))
    return minimum-radius if found else -1


def measure(parts,p,folded=False):
    by={part['name']:part for part in parts};issues=[];pipes=[];supports=[]
    zs=[-p['spacing_12'],0,p['spacing_23']]
    def need(name):
        if name not in by:issues.append('Missing part: '+name)
        return by.get(name)
    def contact(actual,expected,message):
        if abs(actual-expected)>TOL:issues.append(message)
    for i,z in enumerate(zs,1):
        pipe=need(f'pipe{i}_pipe_left');flange=need(f'pipe{i}_flange_left')
        if pipe is None or flange is None:continue
        c=center(pipe);r=p[f'diameter_{i}']/2;h=r+.044+p[f'rise_{i}']
        contact(c[1],h,f'Pipe {i} height mismatch');contact(c[2],z,f'Pipe {i} lateral position mismatch')
        actual_r=max(math.hypot(q[1]-c[1],q[2]-c[2]) for q in pipe['points'])
        flange_r=max(math.hypot(q[1]-c[1],q[2]-c[2]) for q in flange['points'])
        pipes.append(dict(id=i,center_yz=c[1:],outer_radius=actual_r,flange_radius=flange_r,bottom=bounds(pipe)[0][1]))
    gaps=[]
    for a in range(len(pipes)):
        for b in range(a+1,len(pipes)):
            pa,pb=pipes[a],pipes[b];distance=math.dist(pa['center_yz'],pb['center_yz'])
            gap=distance-pa['outer_radius']-pb['outer_radius'];fgap=distance-pa['flange_radius']-pb['flange_radius']
            gaps.append(dict(pipes=[pa['id'],pb['id']],pipe_gap=gap,flange_envelope_gap=fgap))
            if gap<0 or fgap<.04-TOL:issues.append('Pipe/flange envelopes lack required clearance')
    expected=[];x=p['support_pitch']/2
    while x<=p['length']/2-.12+1e-9:
        index=round(x/p['support_pitch']-.5)
        expected.extend([(f'rack_neg_{index}',-x),(f'rack_pos_{index}',x)]);x+=p['support_pitch']
    for kind,count in [('channel_web',len(expected)),('channel_lip',2*len(expected)),('hanger',2*len(expected)),('clamp',3*len(expected))]:
        if sum(v['kind']==kind for v in parts)!=count:issues.append('Missing or duplicate shared support coverage: '+kind)
    for name,x in expected:
        web=need(name+'_web')
        if web is None:continue
        lo,hi=bounds(web);low=zs[0]-p['diameter_1']/2-.25;high=zs[-1]+p['diameter_3']/2+.25
        for actual,value in [(center(web)[0],x),(lo[1],.040),(hi[1],.044),(lo[2],low),(hi[2],high)]:contact(actual,value,'Shared beam position/span mismatch: '+name)
        for side in (-1,1):
            lip=need(name+f'_lip_{side}');rod=need(name+f'_rod_{side}');anchor=need(name+f'_anchor_{side}')
            if lip:
                l,h=bounds(lip)
                for a,b in [(l[1],0),(h[1],lo[1]),(l[2],lo[2]),(h[2],hi[2]),(center(lip)[0],x+side*(.0185 if folded else .0225))]:contact(a,b,'Channel lip mismatch: '+name)
            if rod:
                c=center(rod);rlo,rhi=bounds(rod);z=low+.045 if side<0 else high-.045
                for a,b in [(c[0],x),(c[2],z),(rhi[1],p['hanger_height'])]:contact(a,b,'Hanger position mismatch: '+name)
                if rlo[1]>=lo[1] or hole_clearance(web,c[0],c[2],.004)<=0:issues.append('Hanger misses web hole: '+name)
                if anchor:contact(bounds(anchor)[0][1],rhi[1],'Hanger misses anchor: '+name)
            for y in (.031,.044):
                nut=need(name+f'_nut_{side}_{y}')
                if nut and rod:
                    c=center(nut);rc=center(rod)
                    if math.dist((c[0],c[2]),(rc[0],rc[2]))>TOL:issues.append('Hanger nut alignment mismatch: '+name)
                    contact(bounds(nut)[1 if y<.04 else 0][1],lo[1] if y<.04 else hi[1],'Hanger nut/web contact mismatch: '+name)
        clamps=[]
        for i,z in enumerate(zs,1):
            clamp_name=name+f'_pipe{i}_clamp';clamp=need(clamp_name);pipe=need(f'pipe{i}_pipe_left')
            if clamp is None or pipe is None:continue
            h=center(pipe)[1];r=p[f'diameter_{i}']/2;rise=p[f'rise_{i}'];seat=by.get(name+f'_pipe{i}_seat')
            bearing=hi[1]
            if rise>0:
                seat=need(name+f'_pipe{i}_seat')
                if seat:
                    slo,shi=bounds(seat);bearing=shi[1]
                    contact(slo[1],hi[1],'Seat floats above shared beam: '+name)
                    for actual,value in [(slo[0],x-.018),(shi[0],x+.018),(slo[2],z-.9*r),(shi[2],z+.9*r)]:contact(actual,value,'Seat footprint mismatch: '+name)
            elif seat:issues.append('Unexpected seat under zero-rise pipe: '+name)
            gap=bounds(pipe)[0][1]-bearing;contact(gap,0,'Pipe is not supported by beam/seat: '+clamp_name)
            q=clamp['points'];bottom=min(v[1] for v in q);top=[v for v in q if v[1]>=h-TOL]
            crown=min(math.hypot(v[1]-h,v[2]-z) for v in top)-r if top else -1
            contact(crown,0,'U-bolt crown misses pipe: '+clamp_name)
            if any(v[1]<h-TOL and abs(v[2]-z)<r-TOL for v in q):issues.append('U-bolt must open down: '+clamp_name)
            holes=[]
            for side in (-1,1):
                ring=[v for v in q if abs(v[1]-bottom)<TOL and (v[2]-z)*side>0]
                if len(ring)!=16:issues.append('Missing downward U-bolt leg: '+clamp_name);continue
                cx=sum(v[0] for v in ring)/len(ring);cz=sum(v[2] for v in ring)/len(ring)
                radius=max(math.hypot(v[0]-cx,v[2]-cz) for v in ring)
                clearance=hole_clearance(web,cx,cz,radius);holes.append(clearance)
                if clearance<=0 or bottom>=lo[1]:issues.append('U-bolt leg does not pass real web opening: '+clamp_name)
                washer=need(clamp_name+f'_washer_{side}');nut=need(clamp_name+f'_nut_{side}')
                if washer and nut:
                    for hardware in (washer,nut):
                        c=center(hardware)
                        if math.dist((c[0],c[2]),(cx,cz))>TOL:issues.append('U-bolt hardware alignment mismatch: '+clamp_name)
                    contact(bounds(washer)[1][1],lo[1],'Washer misses web underside: '+clamp_name)
                    contact(bounds(nut)[1][1],bounds(washer)[0][1],'Nut misses washer: '+clamp_name)
                    if bottom>=bounds(nut)[0][1]:issues.append('U-bolt leg does not extend below nut: '+clamp_name)
            clamps.append(dict(pipe=i,bearing_gap=gap,crown_gap=crown,opening='down',leg_hole_clearances=holes))
        supports.append(dict(name=name,x=x,beam_z_bounds=[lo[2],hi[2]],clamps=clamps))
    return dict(passed=not issues,issues=issues,measurements=dict(pipe_count=len(pipes),support_count=len(expected),pipes=pipes,clearances=gaps,supports=supports))
