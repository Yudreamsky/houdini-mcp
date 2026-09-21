"""Measure the actual three-span pipe chain, interfaces and support placement."""
import math
from .rack_checks import bounds,TOL
from .assembly_checks import separation


def measure(parts,p):
    by={v['name']:v for v in parts};issues=[];spans=[];interfaces=[];support_spans=[]
    a=p['joint_offset_3'];b=p['second_joint_offset_3'];cy=.044+p['rise_3']+p['diameter_3']/2;cz=p['spacing_23']
    expected=[('pipe3_pipe_left',-p['length']/2,a-.044),('pipe3_pipe_middle',a+.044,b-.044),('pipe3_pipe_right',b+.044,p['length']/2)]
    for name,low,high in expected:
        part=by.get(name)
        if part is None:issues.append('Missing chain span: '+name);continue
        lo,hi=bounds(part);radii=[math.hypot(q[1]-cy,q[2]-cz) for q in part['points']]
        values=[lo[0]-low,hi[0]-high,(lo[1]+hi[1])/2-cy,(lo[2]+hi[2])/2-cz,
                max(radii)-p['diameter_3']/2,min(radii)-(p['diameter_3']/2-p['wall_3'])]
        if any(abs(v)>TOL for v in values) or hi[0]<=lo[0]:issues.append('Chain span extent/axis/wall mismatch: '+name)
        spans.append(dict(name=name,x=[lo[0],hi[0]],errors=values))
    pipe_names=[v['name'] for v in parts if v['kind']=='pipe' and v['name'].startswith('pipe3_')]
    if set(pipe_names)!={v[0] for v in expected}:issues.append('Unexpected pipe3 span coverage')
    for key,prefix,offset,left_pipe,right_pipe in [('joint_a','pipe3_',a,'pipe3_pipe_left','pipe3_pipe_middle'),('joint_b','pipe3_joint_b_',b,'pipe3_pipe_middle','pipe3_pipe_right')]:
        names=[prefix+'gasket',prefix+'flange_left',prefix+'flange_right',left_pipe,right_pipe]
        if any(n not in by for n in names):issues.append('Missing chain interface: '+key);continue
        body,left,right,pl,pr=[bounds(by[n]) for n in names]
        errors=[body[0][0]-(offset-.044),body[1][0]-(offset+.044),left[1][0]-body[0][0],right[0][0]-body[1][0],pl[1][0]-body[0][0],pr[0][0]-body[1][0]]
        if any(abs(v)>TOL for v in errors):issues.append('Chain interface gap/overlap: '+key)
        interfaces.append(dict(joint=key,errors=errors))
    for web in (v for v in parts if v['kind']=='channel_web'):
        lo,hi=bounds(web);matches=[s['name'] for s in spans if s['x'][0]+TOL<=lo[0] and s['x'][1]-TOL>=hi[0]]
        if len(matches)!=1:issues.append('Support does not bear on exactly one pipe3 span: '+web['name'])
        support_spans.append(dict(support=web['name'],pipe_spans=matches))
    joints=[v for v in parts if v['name'].startswith('pipe3_joint_b_')]
    neighbors=[v for v in parts if v['kind'] in ('clamp','clamp_washer','clamp_nut','channel_web','channel_lip','seat') or (v['name'].startswith('pipe3_') and v['kind']!='pipe' and not v['name'].startswith('pipe3_joint_b_'))]
    clearance=None
    if joints and neighbors:
        gap,j,n=min((separation(bounds(j),bounds(n)),j['name'],n['name']) for j in joints for n in neighbors)
        clearance=dict(aabb_separation_lower_bound=gap,joint_part=j,neighbor=n,visual_margin=.01)
        if gap<.01-TOL:issues.append('Repeated joint neighbor clearance below visual margin')
    else:issues.append('Missing repeated joint/neighbor parts')
    return dict(passed=not issues,issues=issues,measurements=dict(spans=spans,interfaces=interfaces,support_spans=support_spans,second_joint_clearance=clearance),
                scope='Fixed two-joint chain; AABB lower bounds, not general collision or engineering validation')
