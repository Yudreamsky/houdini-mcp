"""External split coupling visual study, not a manufacturer product or joint design."""
import math
try:
    base
except NameError:
    from . import sample_geometry as base

PARAMETERS={
    'length':(.8,.4,2.,'Total pipe sample length (m)'),
    'diameter':(.32,.10,.60,'Pipe outside diameter (m)'),
    'wall':(.008,.002,.030,'Pipe wall (m)'),
    'shell_width':(.09,.05,.16,'Coupling axial width (m)'),
    'joint_offset':(0.,-.2,.2,'Coupling X position (m)'),
    'clocking':(25.,-180.,180.,'Coupling rotation about X (degrees)'),
    'segments':(64,24,96,'Circular segments'),
}
ORANGE=(.65,.16,.035)
METAL=(.44,.48,.52)

def validate(values):
    if set(values)-set(PARAMETERS):raise ValueError('Unknown coupling parameters')
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    for k,v in p.items():
        if type(v) not in (int,float) or not math.isfinite(v) or not PARAMETERS[k][1]<=v<=PARAMETERS[k][2]:raise ValueError('Parameter outside finite bounds: '+k)
    if int(p['segments'])!=p['segments'] or p['segments']%4:raise ValueError('Segments must be a multiple of four')
    if p['wall']>=p['diameter']*.2:raise ValueError('Wall must be less than 20 percent of diameter')
    if abs(p['joint_offset'])+p['shell_width']/2+.08>p['length']/2:raise ValueError('Coupling must leave 80mm pipe beyond each shell end')
    return p

def sector(name,section,start,end,steps):
    m=base.Mesh(name,'housing',ORANGE)
    loops=[[(x,r*math.cos(a),r*math.sin(a)) for x,r in section] for a in [start+(end-start)*i/steps for i in range(steps+1)]]
    m.face(list(reversed(loops[0])));m.face(loops[-1])
    for a,b in zip(loops,loops[1:]):
        for j in range(len(section)):
            k=(j+1)%len(section);m.face([a[j],a[k],b[k],b[j]])
    return m.data()

def build(values):
    p=validate(values);d=p['diameter'];r=d/2;w=p['shell_width'];o=p['joint_offset'];n=int(p['segments']);parts=[]
    for side,lo,hi in [('left',-p['length']/2,o-.006*d),('right',o+.006*d,p['length']/2)]:
        parts.append(base.tube('pipe_'+side,'pipe',lo,hi,r,r-p['wall'],(0,0),(.36,.012,.008),n))
    parts.append(base.tube('seal_envelope','seal',o-w*.36,o+w*.36,r+.006*d,r,(0,0),(.018,.018,.018),n))
    section=[(o-w/2,r+.006*d),(o+w/2,r+.006*d),(o+w/2,r+.035*d),
             (o+w*.36,r+.065*d),(o+w*.15,r+.065*d),(o+w*.10,r+.075*d),
             (o-w*.10,r+.075*d),(o-w*.15,r+.065*d),(o-w*.36,r+.065*d),(o-w/2,r+.035*d)]
    eps=.012
    parts.append(sector('housing_upper',section,-math.pi/2+eps,math.pi/2-eps,n//2))
    parts.append(sector('housing_lower',section,math.pi/2+eps,3*math.pi/2-eps,n//2))
    for side in (-1,1):
        z=side*(r+.12*d)
        for half,lo,hi in [('upper',.01*d,.0625*d),('lower',-.0625*d,-.01*d)]:
            m=base.Mesh(f'lug_{side}_{half}','lug',ORANGE)
            angles=[2*math.pi*j/32 for j in range(32)]
            outside=[(.085*d*math.cos(a),.45*w*math.sin(a)) for a in angles]
            inside=[(.018*d*math.cos(a),.018*d*math.sin(a)) for a in angles]
            base.plate_with_hole(m,outside,inside,lo,hi,lambda y,u,v:(o+v,y,z+u))
            parts.append(m.data())
        parts.append(base.tube(f'bolt_{side}','bolt',-.112*d,.109*d,.013*d,0,(z,o),METAL,24,axis=1))
        for half,lo,hi in [('upper',.0625*d,.075*d),('lower',-.075*d,-.0625*d)]:
            parts.append(base.tube(f'washer_{side}_{half}','washer',lo,hi,.034*d,.016*d,(z,o),METAL,32,axis=1))
        parts.append(base.tube(f'head_{side}','bolt_head',.075*d,.102*d,.030*d,0,(z,o),METAL,6,axis=1))
        parts.append(base.tube(f'nut_{side}','nut',-.102*d,-.075*d,.030*d,.016*d,(z,o),METAL,6,axis=1))
    a=math.radians(p['clocking']);c,s=math.cos(a),math.sin(a)
    for part in parts:
        if part['kind']=='pipe':continue
        for q in part['points']:q[1],q[2]=q[1]*c-q[2]*s,q[1]*s+q[2]*c
    return dict(recipe='external_coupling_sample',parameters=p,parts=parts,units='metres',
                scope='Orange external split coupling with two short pipes; visual reference study only',
                provenance={'visible':'external housing, lug and fastener silhouette','inferred':'symmetric rear half, seal envelope and all numeric dimensions'},
                simplifications=['No identified manufacturer, pressure rating or engineering approval','Separate overlapping lug meshes approximate cast attachments; not a fabrication solid','Pipe grooves, housing keys, seal profile and threads are omitted','Only one coupling; no support or rack integration'])

def cook(node):
    import hou,json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS});g=node.geometry();g.clear()
    name=g.addAttrib(hou.attribType.Prim,'name','');kind=g.addAttrib(hou.attribType.Prim,'part_type','');cd=g.addAttrib(hou.attribType.Prim,'Cd',(1.,1.,1.))
    for part in spec.pop('parts'):
        points=[]
        for q in part['points']:
            point=g.createPoint();point.setPosition(q);points.append(point)
        for face in part['faces']:
            prim=g.createPolygon()
            for i in face:prim.addVertex(points[i])
            prim.setAttribValue(name,part['name']);prim.setAttribValue(kind,part['kind']);prim.setAttribValue(cd,part['color'])
    g.addAttrib(hou.attribType.Global,'sample_spec','');g.setGlobalAttribValue('sample_spec',json.dumps(spec,sort_keys=True))
