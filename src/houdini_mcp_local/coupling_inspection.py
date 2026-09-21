"""Read native Houdini polygons for the external coupling inspector."""
import hashlib,importlib,json
from . import coupling_checks,coupling_geometry

def inspect(node,geometry=None):
    importlib.reload(coupling_checks)
    geo=geometry if geometry is not None else node.geometry()
    if geo is None or node.errors():raise ValueError('Coupling failed to cook')
    p={k:node.evalParm(k) for k in coupling_geometry.PARAMETERS};parts={};digest=hashlib.sha256()
    for prim in geo.prims():
        name=prim.attribValue('name');ids=[v.point().number() for v in prim.vertices()]
        digest.update(json.dumps([name,ids]).encode())
        part=parts.setdefault(name,dict(name=name,kind=prim.attribValue('part_type'),points=[],faces=[],lookup={}))
        face=[]
        for v in prim.vertices():
            point=v.point();key=point.number()
            if key not in part['lookup']:part['lookup'][key]=len(part['points']);part['points'].append(tuple(point.position()))
            face.append(part['lookup'][key])
        part['faces'].append(face)
    for point in geo.points():digest.update(json.dumps(tuple(point.position())).encode())
    result=coupling_checks.measure(list(parts.values()),p)
    return dict(result,path=node.path(),part_count=len(parts),geometry_sha256=digest.hexdigest(),specification=json.loads(geo.attribValue('sample_spec')),world_transform=list(node.parent().worldTransform().asTuple()))
