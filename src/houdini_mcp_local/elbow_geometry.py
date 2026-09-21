"""A horizontal 90-degree routed sample using the unchanged straight recipe.

When embedded, the compiler supplies base as a private module namespace.
"""
import math
try:
    base
except NameError:
    from . import sample_geometry as base

PARAMETERS = {k:v for k,v in base.PARAMETERS.items() if k != 'length'}
PARAMETERS.update({
    'inlet_length': (2.4, 1.2, 6.0, 'Inlet straight length (m)'),
    'outlet_length': (1.8, 1.2, 6.0, 'Outlet straight length (m)'),
    'bend_radius': (.60, .20, 2.0, 'Elbow centerline radius (m)'),
    'bend_segments': (24, 8, 64, 'Elbow arc segments'),
})


def validate(values):
    unknown = set(values)-set(PARAMETERS)
    if unknown: raise ValueError('Unknown elbow parameters: '+', '.join(sorted(unknown)))
    p={k:v[0] for k,v in PARAMETERS.items()}; p.update(values)
    for key,value in p.items():
        _,lo,hi,_=PARAMETERS[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError('Parameter outside finite bounds: '+key)
    if int(p['bend_segments'])!=p['bend_segments']: raise ValueError('Integer bend_segments required')
    if p['bend_radius']<1.5*p['diameter']:
        raise ValueError('This sample requires centerline bend radius >= 1.5 times diameter')
    for side in ('inlet','outlet'): base.validate(leg_parameters(p,side))
    return p


def leg_parameters(p,side):
    return dict({k:p[k] for k in base.PARAMETERS if k!='length'},length=p[side+'_length'])


def place(point,p,side):
    x,y,z=point
    if side=='inlet': return [x-p['inlet_length']/2,y,z]
    return [p['bend_radius']-z,y,p['bend_radius']+p['outlet_length']/2+x]


def elbow(p):
    mesh=base.Mesh('elbow','elbow',(.45,.035,.025))
    n=int(p['segments']); steps=int(p['bend_segments']); radius=p['bend_radius']
    outer=p['diameter']/2; inner=outer-p['wall']; height=outer+.044
    def pos(j,i,r):
        a=(math.pi/2)*j/steps; phi=2*math.pi*i/n
        return [radius*math.sin(a)-r*math.sin(phi)*math.sin(a),
                height+r*math.cos(phi),radius*(1-math.cos(a))+r*math.sin(phi)*math.cos(a)]
    for j in range(steps):
        for i in range(n):
            k=(i+1)%n
            mesh.face([pos(j,i,outer),pos(j,k,outer),pos(j+1,k,outer),pos(j+1,i,outer)])
            mesh.face([pos(j,k,inner),pos(j,i,inner),pos(j+1,i,inner),pos(j+1,k,inner)])
    for i in range(n):
        k=(i+1)%n
        mesh.face([pos(0,i,outer),pos(0,i,inner),pos(0,k,inner),pos(0,k,outer)])
        mesh.face([pos(steps,i,outer),pos(steps,k,outer),pos(steps,k,inner),pos(steps,i,inner)])
    return mesh.data()


def build(values):
    p=validate(values); parts=[]; supports={}
    for side in ('inlet','outlet'):
        leg=base.build(leg_parameters(p,side))
        for part in leg['parts']:
            part['name']=side+'_'+part['name']
            part['points']=[place(point,p,side) for point in part['points']]
            parts.append(part)
        supports[side]=leg['support_positions']
    parts.append(elbow(p))
    r=p['bend_radius']; h=p['diameter']/2+.044
    return dict(parameters=p,parts=parts,units='metres',recipe='pipe_elbow_sample',support_style='u_bolt_v1',
                dimensions_source='illustrative adjustable values, not measured from photograph',
                support_positions=supports,
                ports=[dict(id='inlet',center=[-p['inlet_length'],h,0],outward=[-1,0,0]),
                       dict(id='outlet',center=[r,h,r+p['outlet_length']],outward=[0,0,1])],
                joints=[dict(id='inlet_elbow',center=[0,h,0],axis=[1,0,0]),
                        dict(id='elbow_outlet',center=[r,h,r],axis=[0,0,1])],
                simplifications=['fixed horizontal 90 degree bend','closed component ends meet at internal interfaces',
                                 'faceted circular sweep','same simplified straight-joint hardware as recipe v1'])


def cook(node):
    import hou,json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS})
    geo=node.geometry();geo.clear()
    name=geo.addAttrib(hou.attribType.Prim,'name','');kind=geo.addAttrib(hou.attribType.Prim,'part_type','')
    cd=geo.addAttrib(hou.attribType.Prim,'Cd',(1.,1.,1.))
    for part in spec.pop('parts'):
        points=[]
        for pos in part['points']:
            point=geo.createPoint();point.setPosition(pos);points.append(point)
        group=geo.createPrimGroup(part['name'].replace('-','m').replace('.','_'))
        for indices in part['faces']:
            face=geo.createPolygon()
            for index in indices:face.addVertex(points[index])
            face.setAttribValue(name,part['name']);face.setAttribValue(kind,part['kind']);face.setAttribValue(cd,part['color']);group.add(face)
    geo.addAttrib(hou.attribType.Global,'sample_spec','');geo.setGlobalAttribValue('sample_spec',json.dumps(spec,sort_keys=True))
