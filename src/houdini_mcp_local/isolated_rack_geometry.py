"""User-corrected first joint: one separate rubber buffer per bolt.

Pad dimensions/profile are visual assumptions. Hidden flow/seal parts are unknown.
"""
import math
try:
    repeated
except NameError:
    from . import repeated_rack_geometry as repeated
base=repeated.base
PARAMETERS=dict(repeated.PARAMETERS)
PARAMETERS['pad_radius_ratio']=(.14,.06,.16,'First joint rubber pad outer radius / pipe diameter')


def validate(values):
    if set(values)-set(PARAMETERS):raise ValueError('Unknown isolated rack parameters')
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    repeated.validate({k:p[k] for k in repeated.PARAMETERS})
    r=p['pad_radius_ratio'];d=p['diameter_3']
    if type(r) not in (int,float) or not math.isfinite(r) or not .06<=r<=.16:raise ValueError('Invalid pad radius ratio')
    if 2*.635*math.sin(math.pi/p['bolt_count'])-2*r<.012:raise ValueError('Rubber pads need independent air gaps')
    if (.635-r)*d<d/2-p['wall_3']+.005*d:raise ValueError('Rubber pad intrudes into projected pipe bore')
    if p['spacing_23']<.775*p['diameter_2']+.795*d+.04:raise ValueError('Spacing must clear conservative pad envelope')
    return p


def pad(name,d,ratio,segments,offset,cy,cz):
    mesh=base.Mesh(name,'rubber_pad',(.018,.20,.48))
    profiles=[(-.044,.88),(-.037,1),(.037,1),(.044,.88)]
    outer=[];inner=[]
    for x,scale in profiles:
        outer.append([(offset+x,cy+d*ratio*scale*math.cos(2*math.pi*i/segments),cz+d*ratio*scale*math.sin(2*math.pi*i/segments)) for i in range(segments)])
        inner.append([(offset+x,cy+d*.047*math.cos(2*math.pi*i/segments),cz+d*.047*math.sin(2*math.pi*i/segments)) for i in range(segments)])
    for i in range(segments):
        j=(i+1)%segments
        mesh.face([outer[0][i],inner[0][i],inner[0][j],outer[0][j]])
        mesh.face([outer[-1][i],outer[-1][j],inner[-1][j],inner[-1][i]])
        for k in range(len(profiles)-1):
            mesh.face([outer[k][i],outer[k][j],outer[k+1][j],outer[k+1][i]])
            mesh.face([inner[k][j],inner[k][i],inner[k+1][i],inner[k+1][j]])
    return mesh.data()


def build(values):
    p=validate(values);spec=repeated.build({k:p[k] for k in repeated.PARAMETERS})
    d=p['diameter_3'];cy=.044+p['rise_3']+d/2;cz=p['spacing_23'];added=[]
    for i in range(int(p['bolt_count'])):
        angle=2*math.pi*i/p['bolt_count']
        added.append(pad(f'pipe3_pad_{i:02}',d,p['pad_radius_ratio'],int(p['segments']),p['joint_offset_3'],cy+.635*d*math.cos(angle),cz+.635*d*math.sin(angle)))
    spec['parts']=[v for v in spec['parts'] if v['name']!='pipe3_gasket']+added
    spec.update(parameters=p,recipe='pipe_rack_isolated',joint_style='First pipe3 joint has one independent rubber pad per bolt; other blue bodies are uncorrected legacy geometry',
                replacement=dict(removed=['pipe3_gasket'],added=[v['name'] for v in added],modified=[]),
                internal_flow_connection='unmodeled',
                reference_uncertainties=['User identified independent rubber buffers and isolation purpose; no damping performance verified',
                                         'Pad size, bevel, axial length and bore are visual assumptions, not product specifications',
                                         'Hidden internal flow/seal connection unknown; existing pipe-end gap retained',
                                         'Other two blue bodies retain the rejected continuous-body interpretation pending correction'])
    return spec


def cook(node):
    import hou,json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS});g=node.geometry();g.clear()
    name=g.addAttrib(hou.attribType.Prim,'name','');kind=g.addAttrib(hou.attribType.Prim,'part_type','');cd=g.addAttrib(hou.attribType.Prim,'Cd',(1.,1.,1.))
    for part in spec.pop('parts'):
        pts=[]
        for q in part['points']:
            point=g.createPoint();point.setPosition(q);pts.append(point)
        for face in part['faces']:
            prim=g.createPolygon()
            for i in face:prim.addVertex(pts[i])
            prim.setAttribValue(name,part['name']);prim.setAttribValue(kind,part['kind']);prim.setAttribValue(cd,part['color'])
    g.addAttrib(hou.attribType.Global,'sample_spec','');g.setGlobalAttribValue('sample_spec',json.dumps(spec,sort_keys=True))
