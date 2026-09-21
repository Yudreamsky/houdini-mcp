"""Measure the cooked route and reuse straight-leg checks in each local frame."""
import collections
import hashlib
import json
import math
import hou
from .sample_inspection import inspect_geometry


def inspect(node, geometry=None):
    geo=geometry if geometry is not None else node.geometry()
    if geo is None or node.errors(): raise ValueError('Elbow sample failed to cook')
    keys=('diameter','wall','support_pitch','bolt_count','hanger_height','inlet_length','outlet_length','bend_radius')
    specification=json.loads(geo.attribValue('sample_spec'))
    p={k:node.evalParm(k) for k in keys}; r=p['bend_radius']; h=p['diameter']/2+(.044 if specification.get('support_style')=='u_bolt_v1' else .052)
    issues=[]; legs={}; points={}; parts={}; digest=hashlib.sha256()
    for prim in geo.prims():
        name=prim.attribValue('name'); indices=[v.point().number() for v in prim.vertices()]
        digest.update(json.dumps([name,indices]).encode())
        part=parts.setdefault(name,{'name':name,'kind':prim.attribValue('part_type'),'faces':0})
        part['faces']+=1
        for v in prim.vertices(): points.setdefault(name,{})[v.point().number()]=tuple(v.point().position())
    for point in geo.points(): digest.update(json.dumps(tuple(point.position())).encode())
    for name,part in parts.items():
        q=list(points[name].values());part.update(points=len(q),bbox_min=[min(v[a] for v in q) for a in range(3)],bbox_max=[max(v[a] for v in q) for a in range(3)])
    for side in ('inlet','outlet'):
        # Work on a geometry copy; neither node nor HDA is modified by inspection.
        leg=hou.Geometry();leg.merge(geo)
        leg.deletePrims([v for v in leg.prims() if not v.attribValue('name').startswith(side+'_')],False)
        for prim in leg.prims():prim.setAttribValue('name',prim.attribValue('name')[len(side)+1:])
        for point in leg.points():
            x,y,z=point.position()
            point.setPosition((x+p['inlet_length']/2,y,z) if side=='inlet' else (z-r-p['outlet_length']/2,y,r-x))
        params={k:p[k] for k in ('diameter','wall','support_pitch','bolt_count','hanger_height')}
        params['length']=p[side+'_length']
        legs[side]=inspect_geometry(node,leg,params)
        issues.extend({'leg':side,'issue':issue} for issue in legs[side]['issues'])
        for part in legs[side]['parts']:
            parts[side+'_'+part['name']]['closed_edges']=part['closed_edges']
    elbow_prims=[v for v in geo.prims() if v.attribValue('name')=='elbow']
    edge_counts=collections.Counter();zero=0
    for prim in elbow_prims:
        ids=[v.point().number() for v in prim.vertices()]
        edge_counts.update(tuple(sorted(pair)) for pair in zip(ids,ids[1:]+ids[:1]))
        if prim.intrinsicValue('measuredarea')<=1e-14:zero+=1
    e=list(points.get('elbow',{}).values())
    if not e: issues.append('Missing elbow')
    else:
        closed=all(n==2 for n in edge_counts.values());parts['elbow']['closed_edges']=closed
        if not closed or zero:issues.append('Elbow has open/nonmanifold edges or zero-area faces')
        if any(not math.isfinite(v) for q in e for v in q):issues.append('Elbow has nonfinite points')
    measurements={'legs':{side:v['measurements'] for side,v in legs.items()}}
    if e:
        radii=[math.hypot(q[1]-h,math.hypot(q[0],q[2]-r)-r) for q in e]
        measurements.update(elbow_outer_diameter=2*max(radii),elbow_wall=max(radii)-min(radii))
        for key,expected in [('elbow_outer_diameter',p['diameter']),('elbow_wall',p['wall'])]:
            if abs(measurements[key]-expected)>3e-6:issues.append('Elbow dimension mismatch: '+key)
    def ring(name,axis,high):
        q=list(points.get(name,{}).values())
        if not q:return []
        boundary=(max if high else min)(v[axis] for v in q)
        return [v for v in q if abs(v[axis]-boundary)<2e-6]
    joints=[]
    for label,a,b in [('inlet_elbow',ring('inlet_pipe_right',0,True),ring('elbow',0,False)),
                      ('elbow_outlet',ring('elbow',2,True),ring('outlet_pipe_left',2,False))]:
        error=max(max(min(math.dist(x,y) for y in b) for x in a),max(min(math.dist(y,x) for x in a) for y in b)) if a and b else None
        joints.append(dict(id=label,boundary_match_max_error=error,ring_vertex_counts=[len(a),len(b)]))
        if error is None or error>3e-6 or len(a)!=len(b):issues.append('Mismatched endpoint rings: '+label)
    ports=[]
    for label,q,expected,normal in [
        ('inlet',ring('inlet_pipe_left',0,False),[-p['inlet_length'],h,0],[-1,0,0]),
        ('outlet',ring('outlet_pipe_right',2,True),[r,h,r+p['outlet_length']],[0,0,1])]:
        center=[sum(v[a] for v in q)/len(q) for a in range(3)] if q else None
        if center is None or math.dist(center,expected)>3e-6:issues.append('Port position mismatch: '+label)
        ports.append(dict(id=label,center=center,outward=normal,normal_scope='fixed recipe end plane'))
    measurements.update(joints=joints,ports=ports,support_count=sum(v['measurements'].get('support_count',0) for v in legs.values()))
    expected_names={'elbow'}|{side+'_'+v['name'] for side,leg in legs.items() for v in leg['parts']}
    if set(parts)!=expected_names:issues.append('Unexpected route components')
    return dict(path=node.path(),passed=not issues,issues=issues,measurements=measurements,
                parts=list(parts.values()),part_count=len(parts),geometry_sha256=digest.hexdigest(),
                world_transform=list(node.parent().worldTransform().asTuple()),
                scope='Fixed horizontal 90-degree route: measured component topology, leg dimensions and matching end rings; not general routing, collision or structural certification',
                specification=json.loads(geo.attribValue('sample_spec')))
