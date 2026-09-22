"""Three fixed isolation flange assemblies, each with independent rubber pads."""
import math
try:
    isolated
except NameError:
    from . import isolated_rack_geometry as isolated
PARAMETERS=dict(isolated.PARAMETERS)
PARAMETERS['pad_radius_ratio']=(.14,.06,.16,'All isolation joints: pad outer radius / local pipe diameter')


def validate(values):
    p=isolated.validate(values);d=p['diameter_2'];r=p['pad_radius_ratio']
    if (.635-r)*d<d/2-p['wall_2']+.005*d:raise ValueError('Pipe 2 pad intrudes into projected pipe bore')
    if p['spacing_12']<.775*p['diameter_1']+.795*d+.04:raise ValueError('Pipe 2 pads lack pipe 1 envelope clearance')
    if p['spacing_23']<.795*(d+p['diameter_3'])+.04:raise ValueError('Pad envelopes need neighbor clearance')
    return p


def build(values):
    p=validate(values);spec=isolated.build(p);added=[]
    for prefix,index,offset,z in [('pipe2_',2,p['joint_offset_2'],0),('pipe3_joint_b_',3,p['second_joint_offset_3'],p['spacing_23'])]:
        d=p[f'diameter_{index}'];cy=.044+p[f'rise_{index}']+d/2
        for i in range(int(p['bolt_count'])):
            angle=2*math.pi*i/p['bolt_count']
            added.append(isolated.pad(f'{prefix}pad_{i:02}',d,p['pad_radius_ratio'],int(p['segments']),offset,cy+.635*d*math.cos(angle),z+.635*d*math.sin(angle)))
    removed=['pipe2_gasket','pipe3_joint_b_gasket']
    spec['parts']=[v for v in spec['parts'] if v['name'] not in removed]+added
    spec.update(parameters=p,recipe='pipe_rack_all_pads',joint_style='Three isolation flange assemblies, one independent rubber pad per bolt',
                replacement=dict(removed=removed,added=[v['name'] for v in added],modified=[]),
                internal_flow_connection='unmodeled_at_all_three_isolation_joints',
                reference_uncertainties=['Independent rubber buffers and isolation purpose identified by user; performance unverified',
                                         'Three fixed modeled stations; dimensions, pad shape and 88mm axial span are visual assumptions',
                                         'Hidden flow/seal connections at all three joints are unknown and unmodeled'])
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
