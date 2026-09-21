"""Compose frozen photo-rack and coupling algorithms; replace only red pipe assembly."""
import math
try:
    reference
except NameError:
    from . import reference_geometry as reference,coupling_geometry as coupling
PARAMETERS=dict(reference.PARAMETERS)
PARAMETERS['red_shell_width']=coupling.PARAMETERS['shell_width']
PARAMETERS['red_clocking']=coupling.PARAMETERS['clocking']

def validate(values):
    if set(values)-set(PARAMETERS):raise ValueError('Unknown coupled rack parameters')
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    reference.validate({k:p[k] for k in reference.PARAMETERS})
    for k in ('red_shell_width','red_clocking'):
        v=p[k]
        if type(v) not in (int,float) or not math.isfinite(v) or not PARAMETERS[k][1]<=v<=PARAMETERS[k][2]:raise ValueError('Parameter outside finite bounds: '+k)
    if abs(p['joint_offset_1'])+p['red_shell_width']/2+.08>p['length']/2:raise ValueError('External joint leaves insufficient pipe end clearance')
    x=p['support_pitch']/2
    while x<=p['length']/2-.12+1e-9:
        if any(abs(p['joint_offset_1']-station)<p['red_shell_width']/2+.0245+.01 for station in (-x,x)):
            raise ValueError('External coupling overlaps support clearance band')
        x+=p['support_pitch']
    return p

def build(values):
    p=validate(values);spec=reference.build({k:p[k] for k in reference.PARAMETERS})
    old={v['name']:v for v in spec['parts'] if v['name'].startswith('pipe1_')}
    # Build the verified local joint with short stubs, then extend only its outer pipe ends.
    joint=coupling.build(dict(length=.8,diameter=p['diameter_1'],wall=p['wall_1'],shell_width=p['red_shell_width'],clocking=p['red_clocking'],joint_offset=0,segments=p['segments']))
    y=p['diameter_1']/2+.044+p['rise_1'];z=-p['spacing_12'];offset=p['joint_offset_1']
    for part in joint['parts']:
        original=part['name'];part['name']='pipe1_'+original
        if part['kind']=='pipe':part['color']=old[part['name']]['color']
        for q in part['points']:
            q[0]=(-p['length']/2 if q[0]<0 else p['length']/2) if part['kind']=='pipe' and abs(abs(q[0])-.4)<1e-9 else q[0]+offset
            q[1]+=y;q[2]+=z
    kept=[v for v in spec['parts'] if not v['name'].startswith('pipe1_')]
    replacement={v['name'] for v in joint['parts']}
    spec.update(parts=joint['parts']+kept,parameters=p,recipe='pipe_rack_coupled',
                joint_style='Red external split coupling; two unchanged blue flanged joints',
                replacement=dict(scope='pipe1_*',removed=sorted(set(old)-replacement),added=sorted(replacement-set(old)),modified=sorted(set(old)&replacement),preserved=sorted(v['name'] for v in kept)),
                reference_uncertainties=['All dimensions inferred; no manufacturer or engineering approval','Existing round hangers and upper-frame interpretation unchanged; not full photo reconstruction'],
                simplifications=spec['simplifications']+joint['simplifications'])
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
