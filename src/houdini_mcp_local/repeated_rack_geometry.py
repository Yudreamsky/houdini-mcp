"""Fixed two-joint chain on pipe 3; compose the frozen single-coupling rack."""
import copy
import math
try:
    coupled
except NameError:
    from . import coupled_rack_geometry as coupled
base=coupled.reference.base
PARAMETERS=dict(coupled.PARAMETERS)
PARAMETERS['second_joint_offset_3']=(.98,.35,4.0,'Pipe 3 second blue joint X position (m)')


def validate(values):
    if set(values)-set(PARAMETERS):raise ValueError('Unknown repeated rack parameters')
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    coupled.validate({k:p[k] for k in coupled.PARAMETERS})
    b=p['second_joint_offset_3'];a=p['joint_offset_3'];reach=.069+.11*p['diameter_3']
    if type(b) not in (int,float) or not math.isfinite(b) or not .35<=b<=4:
        raise ValueError('Parameter outside finite bounds: second_joint_offset_3')
    if b+reach+.08>p['length']/2:raise ValueError('Second joint leaves insufficient right pipe end')
    if b-a<2*reach+.08:raise ValueError('Repeated joint hardware lacks axial separation')
    x=p['support_pitch']/2
    while x<=p['length']/2-.12+1e-9:
        if any(abs(b-station)<reach+.035 for station in (-x,x)):
            raise ValueError('Second joint overlaps a support station clearance band')
        x+=p['support_pitch']
    return p


def build(values):
    p=validate(values);spec=coupled.build({k:p[k] for k in coupled.PARAMETERS})
    a=p['joint_offset_3'];b=p['second_joint_offset_3'];parts=spec['parts']
    added=[]
    for part in parts:
        if part['name']=='pipe3_pipe_right':
            for q in part['points']:
                if abs(q[0]-(a+.044))<1e-8:q[0]=b+.044
        elif part['name'].startswith('pipe3_') and part['kind']!='pipe':
            new=copy.deepcopy(part);new['name']='pipe3_joint_b_'+part['name'][6:]
            for q in new['points']:q[0]+=b-a
            added.append(new)
    middle=base.tube('pipe3_pipe_middle','pipe',a+.044,b-.044,p['diameter_3']/2,
                     p['diameter_3']/2-p['wall_3'],(p['diameter_3']/2+.044+p['rise_3'],p['spacing_23']),
                     next(v['color'] for v in parts if v['name']=='pipe3_pipe_right'),int(p['segments']))
    parts.extend([middle]+added)
    spec.update(parameters=p,recipe='pipe_rack_repeated',
                joint_style='One red external coupling, one blue joint on pipe 2, two blue joints on pipe 3',
                pipe3_chain=['pipe3_pipe_left','joint_a','pipe3_pipe_middle','joint_b','pipe3_pipe_right'],
                joint_positions={'joint_a':a,'joint_b':b},
                replacement=dict(scope='pipe3 repeated joint',modified=['pipe3_pipe_right'],removed=[],
                                 added=[middle['name']]+[v['name'] for v in added]),
                reference_uncertainties=['Repeated blue components visible; count of two and spacing are a bounded visual study',
                                         'Blue body remains an unidentified visual template; upper slotted framing not reconstructed'])
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
