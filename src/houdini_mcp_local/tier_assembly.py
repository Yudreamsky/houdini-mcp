"""Embedded module for the captured two-station assembly HDA.

Only upper-tier height is variable. Geometry, identities and both host stations
come from the accepted snapshot. No repo imports or scene-path dependencies.
"""
import collections
import json
import math
import hou

KIND = 'two_tier_snapshot_v1'
MOVING = ('upper_crossarm', 'rear_upper_crossarm', 'upper_duct_left', 'upper_duct_right')
STATIONS = (('upper_crossarm', ('frame_redside', 'frame_blackside')),
            ('rear_upper_crossarm', ('rear_frame_redside', 'rear_frame_blackside')))


def manifest(node):
    return json.loads(node.type().definition().sections()['AssemblyManifest'].contents())


def cook(sop):
    node = sop.parent()
    spec = manifest(node)
    height = node.evalParm('tier_y')
    if not math.isfinite(height) or not spec['height_min'] <= height <= spec['height_max']:
        raise ValueError('Height outside verified visual envelope')
    geo = sop.geometry()
    geo.clear()
    geo.merge(sop.inputs()[0].geometry())
    delta = height - spec['base_height']
    indices = {v.point().number() for p in geo.prims() if p.attribValue('name') in MOVING for v in p.vertices()}
    if delta:
        for point in geo.points():
            if point.number() in indices:
                position = point.position(); position[1] += delta; point.setPosition(position)
    geo.addAttrib(hou.attribType.Global, 'assembly_height', 0.0)
    geo.setGlobalAttribValue('assembly_height', height)


def subset(geo, names):
    result = hou.Geometry(); result.merge(geo)
    result.deletePrims([p for p in result.prims() if p.attribValue('name') not in names])
    return result


def bounds(geo):
    box = geo.boundingBox(); return [list(box.minvec()), list(box.maxvec())]


def ray(geo, origin, direction):
    hit = hou.Vector3()
    index = geo.intersect(hou.Vector3(origin), hou.Vector3(direction), hit, hou.Vector3(), hou.Vector3(),
                          min_hit=1e-7, max_hit=.004, tolerance=1e-7)
    return index, list(hit)


def inspect_geometry(geo, base, spec, height):
    issues = []
    counts = collections.Counter(geo.primStringAttribValues('name'))
    if dict(counts) != spec['face_counts'] or '' in counts:
        issues.append('Component identity or face coverage changed')
    if len(geo.points()) != len(base.points()) or len(geo.prims()) != len(base.prims()):
        issues.append('Snapshot topology count changed')
    for key in ('name', 'part_type', 'shop_materialpath'):
        if geo.primStringAttribValues(key) != base.primStringAttribValues(key):
            issues.append('Primitive attribute changed: ' + key)
    if geo.primFloatAttribValues('Cd') != base.primFloatAttribValues('Cd'):
        issues.append('Primitive color changed')
    if geo.vertexFloatAttribValues('N') != base.vertexFloatAttribValues('N'):
        issues.append('Vertex normals changed')
    if [tuple(v.point().number() for v in p.vertices()) for p in geo.prims()] != [tuple(v.point().number() for v in p.vertices()) for p in base.prims()]:
        issues.append('Face connectivity changed')
    moving = {v.point().number() for p in base.prims() if p.attribValue('name') in MOVING for v in p.vertices()}
    before, after = base.pointFloatAttribValues('P'), geo.pointFloatAttribValues('P')
    delta = height - spec['base_height']
    if len(before) != len(after) or any(
        not math.isfinite(value) or
        (abs(value - (before[i] + (delta if i % 3 == 1 else 0))) > 2e-7 if i // 3 in moving else value != before[i])
        for i, value in enumerate(after)
    ):
        issues.append('Unexpected member motion or nonfinite point')
    if issues:
        return dict(passed=False, issues=issues, component_count=len(counts))

    duct = subset(geo, ('upper_duct_left', 'upper_duct_right'))
    segments = {name: bounds(subset(geo, (name,))) for name in ('upper_duct_left', 'upper_duct_right')}
    station_results = []
    for arm_name, frame_names in STATIONS:
        arm = subset(geo, (arm_name,)); ab = bounds(arm)
        x = (ab[0][0] + ab[1][0]) / 2; y = ab[1][1]
        hits = 0
        for dx in (-.018, -.014, .014, .018):
            for fraction in (.15, .30, .50, .70, .85):
                z = spec['duct_center_z'] + spec['duct_width'] * (fraction - .5)
                ia, a = ray(arm, (x+dx, y+.001, z), (0,-1,0))
                ib, b = ray(duct, (x+dx, y-.001, z), (0,1,0))
                if ia >= 0 and ib >= 0 and abs(a[1]-b[1]) < 3e-6: hits += 1
        covers = [name for name, box in segments.items() if box[0][0] < ab[0][0]-.001 and box[1][0] > ab[1][0]+.001]
        end_checks = []
        for frame_name, side in zip(frame_names, (-1, 1)):
            frame = subset(geo, (frame_name,)); fb = bounds(frame)
            plane = fb[1 if side < 0 else 0][2]; end = ab[0 if side < 0 else 1][2]
            contacts = 0
            for i in range(13):
                sx = ab[0][0] + (ab[1][0]-ab[0][0])*(i+.5)/13
                for fraction in (.02,.04,.08,.25,.50,.93,.97):
                    sy = ab[0][1] + (ab[1][1]-ab[0][1])*fraction
                    ia,a = ray(arm,(sx,sy,plane+side*.001),(0,0,-side))
                    ib,b = ray(frame,(sx,sy,plane-side*.001),(0,0,side))
                    if ia >= 0 and ib >= 0 and abs(a[2]-plane)<3e-6 and abs(b[2]-plane)<3e-6: contacts += 1
            end_checks.append(dict(frame=frame_name, gap=end-plane, samples=contacts,
                                   passed=abs(end-plane)<3e-6 and contacts>=6 and fb[0][1]<=ab[0][1] and fb[1][1]>=ab[1][1]))
        station_results.append(dict(arm=arm_name, bearing_samples=hits, covers=covers, ends=end_checks,
                                    passed=hits==20 and len(covers)==1 and abs(y-height)<3e-6 and all(e['passed'] for e in end_checks)))
    if not all(r['passed'] for r in station_results): issues.append('Bearing or T-end relation failed')
    if sorted(n for r in station_results for n in r['covers']) != sorted(segments): issues.append('Incomplete longitudinal support coverage')
    # Moving envelope must stay separated from fixed pipes/joints; fixed uprights are intended contacts.
    moving_boxes = [bounds(subset(geo, (name,))) for name in MOVING]
    fixed_names = set(counts)-set(MOVING)-{n for _,frames in STATIONS for n in frames}
    boxes = {}
    for primitive in geo.prims():
        name=primitive.attribValue('name')
        if name not in fixed_names: continue
        box=boxes.setdefault(name, [[float('inf')]*3,[-float('inf')]*3])
        for vertex in primitive.vertices():
            for axis,value in enumerate(vertex.point().position()):
                box[0][axis]=min(box[0][axis],value);box[1][axis]=max(box[1][axis],value)
    clearance = min(math.sqrt(sum(max(a[0][i]-b[1][i],b[0][i]-a[1][i],0)**2 for i in range(3))) for a in moving_boxes for b in boxes.values())
    if clearance <= .001: issues.append('Moving-to-fixed clearance cannot be proven')
    return dict(passed=not issues, issues=issues, component_count=len(counts), fixed_components=len(counts)-len(MOVING),
                moving_components=list(MOVING), tier_y=height, stations=station_results,
                minimum_aabb_clearance=clearance, scope='Snapshot geometry and visual contacts, not structural design')


def inspect(node):
    node.cook(force=True)
    if node.errors(): raise ValueError('Assembly cook failed: '+str(node.errors()))
    return inspect_geometry(node.geometry(), node.node('snapshot').geometry(), manifest(node), node.evalParm('tier_y'))
