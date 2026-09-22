"""Actual three-pipe assembly inspection, plus the established pipe-joint checks."""
import collections
import hashlib
import importlib
import json
import math
import hou
from . import rack_checks
from .sample_inspection import inspect_geometry


def inspect(node,geometry=None):
    isolated=node.userData('workai_recipe')=='pipe_rack_isolated'
    lobed=node.userData('workai_recipe')=='pipe_rack_lobed'
    repeated=isolated or lobed or node.userData('workai_recipe')=='pipe_rack_repeated'
    coupled=repeated or node.userData('workai_recipe')=='pipe_rack_coupled'
    if isolated:
        from .isolated_rack_geometry import PARAMETERS
    elif lobed:
        from .lobed_rack_geometry import PARAMETERS
    elif repeated:
        from .repeated_rack_geometry import PARAMETERS
    elif coupled:
        from .coupled_rack_geometry import PARAMETERS
    elif node.userData('workai_recipe')=='pipe_rack_reference':
        from .reference_geometry import PARAMETERS
    else:
        from .rack_geometry import PARAMETERS
    importlib.reload(rack_checks)
    geo=geometry if geometry is not None else node.geometry()
    if geo is None or node.errors():raise ValueError('Rack sample failed to cook')
    p={k:node.evalParm(k) for k in PARAMETERS};parts={};digest=hashlib.sha256();issues=[]
    for prim in geo.prims():
        name=prim.attribValue('name');ids=[v.point().number() for v in prim.vertices()]
        digest.update(json.dumps([name,ids]).encode())
        part=parts.setdefault(name,dict(name=name,kind=prim.attribValue('part_type'),points=[],faces=[],lookup={},zero=0))
        local=[]
        for v in prim.vertices():
            point=v.point();key=point.number()
            if key not in part['lookup']:part['lookup'][key]=len(part['points']);part['points'].append(tuple(point.position()))
            local.append(part['lookup'][key])
        part['faces'].append(local)
        if prim.intrinsicValue('measuredarea')<=1e-14:part['zero']+=1
    for point in geo.points():digest.update(json.dumps(tuple(point.position())).encode())
    summaries=[]
    for part in parts.values():
        edges=collections.Counter(tuple(sorted((a,b))) for f in part['faces'] for a,b in zip(f,f[1:]+f[:1]))
        closed=all(v==2 for v in edges.values());lo,hi=rack_checks.bounds(part)
        if not closed or part['zero'] or any(not math.isfinite(v) for q in part['points'] for v in q):issues.append('Invalid mesh: '+part['name'])
        summaries.append(dict(name=part['name'],kind=part['kind'],points=len(part['points']),faces=len(part['faces']),bbox_min=lo,bbox_max=hi,closed_edges=closed))
    joint_parts={1:[v['name'] for v in parts.values() if v['name'].startswith('pipe1_') and v['kind']!='pipe']} if coupled else None
    if isolated:joint_parts[3]=['pipe3_flange_left']+[v['name'] for v in parts.values() if v['kind']=='rubber_pad']
    if lobed:joint_parts[3]=['pipe3_flange_left','pipe3_gasket']
    result=rack_checks.measure(list(parts.values()),p,folded=json.loads(geo.attribValue('sample_spec')).get('channel_profile')=='folded_return_v1',joint_parts=joint_parts);issues.extend(result['issues']);joints={}
    for i,z in enumerate((-p['spacing_12'],0,p['spacing_23']),1):
        if (coupled and i==1) or (repeated and i==3):continue
        leg=hou.Geometry();leg.merge(geo);prefix=f'pipe{i}_'
        leg.deletePrims([v for v in leg.prims() if not v.attribValue('name').startswith(prefix)],False)
        for prim in leg.prims():prim.setAttribValue('name',prim.attribValue('name')[len(prefix):])
        for point in leg.points():
            x,y,cz=point.position();point.setPosition((x,y-p[f'rise_{i}'],cz-z))
        spec=json.loads(leg.attribValue('sample_spec'));spec['support_style']='u_bolt_v1';leg.setGlobalAttribValue('sample_spec',json.dumps(spec))
        params={k:p[k] for k in ('length','support_pitch','hanger_height','bolt_count')}
        params.update(diameter=p[f'diameter_{i}'],wall=p[f'wall_{i}'])
        checked=inspect_geometry(node,leg,params,check_supports=False);joints[str(i)]=checked['measurements']
        issues.extend(dict(pipe=i,issue=e) for e in checked['issues'])
    if node.userData('workai_recipe') in ('pipe_rack_reference','pipe_rack_coupled','pipe_rack_repeated','pipe_rack_lobed','pipe_rack_isolated'):
        for i in ((2,) if repeated else (2,3) if coupled else (1,2,3)):
            names=[f'pipe{i}_'+v for v in ('gasket','flange_left','flange_right','pipe_left','pipe_right')]
            if any(v not in parts for v in names):continue
            body,left,right,pl,pr=[rack_checks.bounds(parts[v]) for v in names]
            values=[body[0][0]-(p[f'joint_offset_{i}']-.044),body[1][0]-(p[f'joint_offset_{i}']+.044),
                    left[1][0]-body[0][0],right[0][0]-body[1][0],pl[1][0]-body[0][0],pr[0][0]-body[1][0]]
            joints[str(i)]['body_axial_length']=body[1][0]-body[0][0]
            joints[str(i)]['joint_contact_errors']=values
            if any(abs(v)>3e-6 for v in values):issues.append(f'Photo joint {i} offset/body/pipe interfaces mismatch')
    extra={}
    if isolated:
        from . import pad_checks
        importlib.reload(pad_checks)
        pads=pad_checks.measure(list(parts.values()),p);issues.extend(pads['issues']);extra['rubber_pads']=pads
    if lobed:
        from . import lobed_checks
        importlib.reload(lobed_checks)
        blue=lobed_checks.measure(list(parts.values()),p);issues.extend(blue['issues']);extra['lobed_body']=blue
    if repeated:
        from . import repeated_checks
        importlib.reload(repeated_checks)
        chain=repeated_checks.measure(list(parts.values()),p,discrete_first=isolated);issues.extend(chain['issues']);extra['repeated_chain']=chain
        # Inspect each actual joint and its adjacent actual spans independently.
        for label,prefix,left,right,length in [
            ('3a','pipe3_','pipe3_pipe_left','pipe3_pipe_middle',p['length']/2+p['second_joint_offset_3']-.044),
            ('3b','pipe3_joint_b_','pipe3_pipe_middle','pipe3_pipe_right',p['length']/2-p['joint_offset_3']-.044)]:
            chosen={v['name'] for v in parts.values() if v['name'].startswith(prefix) and v['kind']!='pipe' and (label=='3b' or not v['name'].startswith('pipe3_joint_b_'))}
            chosen.update((left,right));leg=hou.Geometry();leg.merge(geo)
            leg.deletePrims([v for v in leg.prims() if v.attribValue('name') not in chosen],False)
            for prim in leg.prims():
                name=prim.attribValue('name');prim.setAttribValue('name','pipe_left' if name==left else 'pipe_right' if name==right else name[len(prefix):])
            for point in leg.points():
                x,y,z=point.position();point.setPosition((x,y-p['rise_3'],z-p['spacing_23']))
            spec=json.loads(leg.attribValue('sample_spec'));spec['support_style']='u_bolt_v1';leg.setGlobalAttribValue('sample_spec',json.dumps(spec))
            params=dict(length=length,diameter=p['diameter_3'],wall=p['wall_3'],bolt_count=p['bolt_count'])
            checked=inspect_geometry(node,leg,params,check_supports=False,require_gasket=not(isolated and label=='3a'));joints[label]=checked['measurements'];issues.extend(dict(joint=label,issue=e) for e in checked['issues'])
    if coupled:
        from . import coupling_checks,assembly_checks
        importlib.reload(coupling_checks);importlib.reload(assembly_checks)
        red=[];cy=p['diameter_1']/2+.044+p['rise_1'];cz=-p['spacing_12']
        for v in parts.values():
            if v['name'].startswith('pipe1_'):
                red.append(dict(v,name=v['name'][6:],points=[(x,y-cy,z-cz) for x,y,z in v['points']]))
        cp=dict(length=p['length'],diameter=p['diameter_1'],wall=p['wall_1'],shell_width=p['red_shell_width'],joint_offset=p['joint_offset_1'],clocking=p['red_clocking'],segments=p['segments'])
        check=coupling_checks.measure(red,cp);joints['1']=check['measurements'];issues.extend(check['issues'])
        clearance=assembly_checks.coupling_clearances(list(parts.values()));issues.extend(clearance['issues']);extra['coupling_neighbors']=clearance
    return dict(path=node.path(),passed=not issues,issues=issues,measurements=dict(result['measurements'],joints=joints,**extra),parts=summaries,
                part_count=len(summaries),geometry_sha256=digest.hexdigest(),world_transform=list(node.parent().worldTransform().asTuple()),
                specification=json.loads(geo.attribValue('sample_spec')),
                scope='Three parallel pipe envelopes, selected shared bearing/fastener/hole relationships, joint dimensions and mesh topology; not general collisions or engineering certification')
