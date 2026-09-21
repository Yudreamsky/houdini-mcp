"""Inspect actual cooked geometry; expected dimensions come from public parameters."""
import collections
import hashlib
import json
import math
import hou


def inspect(path):
    from .procedural_assets import managed
    node=managed(path)
    if node.userData('workai_recipe')=='pipe_elbow_sample':
        import importlib
        from . import elbow_inspection
        importlib.reload(elbow_inspection)
        return elbow_inspection.inspect(node)
    p={k:node.evalParm(k) for k in ('diameter','length','wall','support_pitch','bolt_count','hanger_height')}
    return inspect_geometry(node,node.geometry(),p)


def inspect_geometry(node,geo,p):
    if geo is None or node.errors(): raise ValueError('Sample failed to cook')
    specification=json.loads(geo.attribValue('sample_spec'))
    u_bolt_style=specification.get('support_style')=='u_bolt_v1'
    parts={}; issues=[]; fingerprint=hashlib.sha256()
    for primitive in geo.prims():
        name=primitive.attribValue('name'); kind=primitive.attribValue('part_type')
        part=parts.setdefault(name,{'kind':kind,'points':{},'edges':collections.Counter(),'faces':0,'zero_area':0})
        indices=[v.point().number() for v in primitive.vertices()]
        fingerprint.update(json.dumps([name,indices]).encode())
        for vertex in primitive.vertices():
            point=vertex.point(); part['points'][point.number()]=tuple(point.position())
        for a,b in zip(indices,indices[1:]+indices[:1]): part['edges'][tuple(sorted((a,b)))]+=1
        part['faces']+=1
        if primitive.intrinsicValue('measuredarea')<=1e-14: part['zero_area']+=1
    for point in geo.points(): fingerprint.update(json.dumps(tuple(point.position())).encode())
    result=[]
    for name,part in sorted(parts.items()):
        points=list(part['points'].values()); mins=[min(p[a] for p in points) for a in range(3)]; maxs=[max(p[a] for p in points) for a in range(3)]
        bad=sum(n!=2 for n in part['edges'].values())
        if bad or part['zero_area'] or any(not math.isfinite(v) for p in points for v in p):
            issues.append(dict(part=name,nonmanifold_or_open_edges=bad,zero_area_faces=part['zero_area']))
        result.append(dict(name=name,kind=part['kind'],bbox_min=mins,bbox_max=maxs,faces=part['faces'],points=len(points),closed_edges=bad==0))
    byname={v['name']:v for v in result}
    required=('pipe_left','pipe_right','flange_left','flange_right','gasket')
    if any(k not in byname for k in required): issues.append('Missing core parts')
    measurements={}
    if all(k in byname for k in required):
        center_y=p['diameter']/2+(.044 if u_bolt_style else .052)
        pipe_points=list(parts['pipe_left']['points'].values())
        radii=[math.hypot(q[1]-center_y,q[2]) for q in pipe_points]
        measurements.update(pipe_outer_diameter=2*max(radii),pipe_wall=max(radii)-min(radii),
                            total_pipe_length=byname['pipe_right']['bbox_max'][0]-byname['pipe_left']['bbox_min'][0],
                            flange_outer_diameter=2*max(math.hypot(q[1]-center_y,q[2]) for q in parts['flange_left']['points'].values()))
        expected={'pipe_outer_diameter':p['diameter'],'pipe_wall':p['wall'],'total_pipe_length':p['length'],'flange_outer_diameter':p['diameter']*1.55}
        for key,value in expected.items():
            if abs(measurements[key]-value)>2e-6: issues.append(dict(measurement=key,expected=value,actual=measurements[key]))
        count=sum(v['kind']=='bolt' for v in result)
        if count!=p['bolt_count']: issues.append('Unexpected flange bolt count')
        clearances=[]
        for bolt in (v for v in result if v['kind']=='bolt'):
            cy=(bolt['bbox_min'][1]+bolt['bbox_max'][1])/2; cz=(bolt['bbox_min'][2]+bolt['bbox_max'][2])/2
            radius=max(math.hypot(q[1]-cy,q[2]-cz) for q in parts[bolt['name']]['points'].values())
            if abs(math.hypot(cy-center_y,cz)-p['diameter']*.635)>2e-6: issues.append('Bolt is off its intended circle: '+bolt['name'])
            for flange_name in ('flange_left','flange_right'):
                f=byname[flange_name]
                if bolt['bbox_min'][0]>f['bbox_min'][0] or bolt['bbox_max'][0]<f['bbox_max'][0]: issues.append('Bolt does not span flange: '+bolt['name'])
                distance=min(math.hypot(q[1]-cy,q[2]-cz) for q in parts[flange_name]['points'].values())
                clearances.append(distance-radius)
        if any(g<=0 for g in clearances): issues.append('Bolt does not fit its flange opening')
        measurements['minimum_bolt_hole_radial_clearance']=min(clearances) if clearances else None
        for flange_name in ('flange_left','flange_right'):
            f=parts[flange_name]
            if len(f['points'])-len(f['edges'])+f['faces'] != -2*p['bolt_count']:
                issues.append('Flange bore/bolt-hole topology mismatch: '+flange_name)
        webs=[v for v in result if v['kind']=='channel_web']; clamps=[v for v in result if v['kind']=='clamp']
        expected_supports=2*(math.floor((p['length']/2-.12-p['support_pitch']/2+1e-9)/p['support_pitch'])+1)
        if len(webs)!=expected_supports or len(clamps)!=expected_supports: issues.append('Missing or duplicate support coverage')
        gaps=[];clamp_checks=[]
        for web in webs:
            name=web['name'].removesuffix('_web')+'_clamp'
            if name not in byname: continue
            clamp=byname[name]
            if not u_bolt_style:
                # Read-only inspection of retained legacy HDA definitions.
                gaps.append(clamp['bbox_min'][1]-web['bbox_max'][1])
                x=(web['bbox_min'][0]+web['bbox_max'][0])/2
                if abs(x)>p['length']/2-.12+1e-6:issues.append('Support outside intended pipe span')
                continue
            # The pipe rests on the web; the U-bolt has no bottom bridge.
            pipe_name='pipe_left' if web['bbox_min'][0]<0 else 'pipe_right'
            gaps.append(byname[pipe_name]['bbox_min'][1]-web['bbox_max'][1])
            x=(web['bbox_min'][0]+web['bbox_max'][0])/2
            if abs(x)>p['length']/2-.12+1e-6: issues.append('Support outside intended pipe span')
            q=list(parts[name]['points'].values());bottom=min(v[1] for v in q)
            upper=[v for v in q if v[1]>=center_y-1e-7]
            radial=min(math.hypot(v[1]-center_y,v[2]) for v in upper) if upper else 0
            if abs(radial-p['diameter']/2)>2e-6:issues.append('U-bolt does not contact pipe crown: '+name)
            if any(v[1]<center_y-1e-6 and abs(v[2])<p['diameter']/2-2e-6 for v in q):issues.append('Clamp has material below the pipe center instead of an open U: '+name)
            leg_clearances=[]
            for side in (-1,1):
                ring=[v for v in q if abs(v[1]-bottom)<2e-6 and v[2]*side>0]
                if not ring:issues.append('Missing downward U-bolt leg: '+name);continue
                cx=sum(v[0] for v in ring)/len(ring);cz=sum(v[2] for v in ring)/len(ring)
                radius=max(math.hypot(v[0]-cx,v[2]-cz) for v in ring)
                clearance=min(math.hypot(v[0]-cx,v[2]-cz) for v in parts[web['name']]['points'].values())-radius
                leg_clearances.append(clearance)
                if clearance<=0 or bottom>=web['bbox_min'][1]:issues.append('U-bolt leg misses/does not pass through channel opening: '+name)
                washer_name=name+f'_washer_{side}';nut_name=name+f'_nut_{side}'
                if washer_name not in byname or nut_name not in byname:issues.append('Missing U-bolt washer/nut: '+name);continue
                washer=byname[washer_name];nut=byname[nut_name]
                for hardware in (washer,nut):
                    hc=[(hardware['bbox_min'][a]+hardware['bbox_max'][a])/2 for a in (0,2)]
                    if math.dist(hc,[cx,cz])>2e-6:issues.append('U-bolt hardware is not aligned with leg: '+hardware['name'])
                if abs(washer['bbox_max'][1]-web['bbox_min'][1])>2e-6 or abs(nut['bbox_max'][1]-washer['bbox_min'][1])>2e-6 or bottom>=nut['bbox_min'][1]:
                    issues.append('U-bolt hardware does not clamp the channel underside: '+name)
            clamp_checks.append(dict(name=name,opening='down',crown_contact_gap=radial-p['diameter']/2,leg_hole_clearances=leg_clearances))
        measurements.update(support_count=len(webs),bolt_count=count,support_style='u_bolt_v1' if u_bolt_style else 'legacy_closed_ring')
        if u_bolt_style:measurements.update(pipe_web_contact_gaps=gaps,u_bolts=clamp_checks)
        else:measurements['support_clamp_contact_gaps']=gaps
        if any(abs(g)>2e-6 for g in gaps): issues.append('Support contact gap')
    return dict(path=node.path(),passed=not issues,issues=issues,measurements=measurements,parts=result,
                part_count=len(result),geometry_sha256=fingerprint.hexdigest(),
                world_transform=list(node.parent().worldTransform().asTuple()),
                scope='Local-space sample dimensions, component topology and selected interface checks; not general collision or structural certification',
                specification=specification)
