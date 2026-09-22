"""One photo-guided lobed blue body; hidden profile and dimensions are inferred."""
import math
try:
    repeated
except NameError:
    from . import repeated_rack_geometry as repeated
base=repeated.base
PARAMETERS=dict(repeated.PARAMETERS)
PARAMETERS['blue_lobe_depth']=(.20,.12,.22,'Pipe 3 first blue body radial lobe depth / pipe diameter')


def validate(values):
    if set(values)-set(PARAMETERS):raise ValueError('Unknown lobed rack parameters')
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    repeated.validate({k:p[k] for k in repeated.PARAMETERS})
    v=p['blue_lobe_depth']
    if type(v) not in (int,float) or not math.isfinite(v) or not .12<=v<=.22:raise ValueError('Invalid blue lobe depth')
    if p['spacing_23']<.775*p['diameter_2']+.82*p['diameter_3']+.04:
        raise ValueError('Spacing must clear conservative blue lobe envelope')
    return p


def blue_body(d,wall,count,segments,depth,offset,cy,cz):
    """Single welded manifold, central bore plus count actual axial bolt holes.

    Sectors share radial boundaries; end collars taper to a raised middle band.
    """
    mesh=base.Mesh('pipe3_gasket','gasket',(.018,.20,.48))
    ri=d/2-wall;bc=.635*d;hole=.047*d
    steps=max(8,2*math.ceil(segments/count/2))
    profiles=[(-.044,.75),(-.032,.75),(-.024,1),(.024,1),(.032,.75),(.044,.75)]
    for k in range(count):
        a=2*math.pi*k/count;low=a-math.pi/count;high=a+math.pi/count
        center=(bc*math.cos(a),bc*math.sin(a))
        boundary=[]
        for j in range(steps+1):
            angle=low+(high-low)*j/steps;bump=(1+math.cos((angle-a)*count))/2
            boundary.append((angle,True,bump))
        boundary += [(high-(high-low)*j/steps,False,0) for j in range(steps+1)]
        def yz(item,scale):
            angle,outer,bump=item;r=d*(.60+depth*bump*scale) if outer else ri
            return (r*math.cos(angle),r*math.sin(angle))
        boundary.sort(key=lambda item:math.atan2(yz(item,1)[1]-center[1],yz(item,1)[0]-center[0]))
        holes=[]
        for item in boundary:
            y,z=yz(item,1);t=math.atan2(z-center[1],y-center[0]);holes.append((center[0]+hole*math.cos(t),center[1]+hole*math.sin(t)))
        outer=[[ (offset+x,cy+y,cz+z) for y,z in (yz(v,scale) for v in boundary)] for x,scale in profiles]
        inner=[[(offset+x,cy+y,cz+z) for y,z in holes] for x,_ in profiles]
        for i in range(len(boundary)):
            j=(i+1)%len(boundary)
            mesh.face([outer[0][i],inner[0][i],inner[0][j],outer[0][j]])
            mesh.face([outer[-1][i],outer[-1][j],inner[-1][j],inner[-1][i]])
            y,z=yz(boundary[i],1);u,v=yz(boundary[j],1)
            omit=abs(y*v-z*u)<1e-10
            for layer in range(len(profiles)-1):
                if not omit:mesh.face([outer[layer][i],outer[layer][j],outer[layer+1][j],outer[layer+1][i]])
                mesh.face([inner[layer][j],inner[layer][i],inner[layer+1][i],inner[layer+1][j]])
    return mesh.data()


def build(values):
    p=validate(values);spec=repeated.build({k:p[k] for k in repeated.PARAMETERS})
    replacement=blue_body(p['diameter_3'],p['wall_3'],int(p['bolt_count']),int(p['segments']),p['blue_lobe_depth'],p['joint_offset_3'],.044+p['rise_3']+p['diameter_3']/2,p['spacing_23'])
    spec['parts']=[replacement if v['name']=='pipe3_gasket' else v for v in spec['parts']]
    spec.update(parameters=p,recipe='pipe_rack_lobed',blue_body_style='first_pipe3_lobed_collared_v1',
                replacement=dict(modified=['pipe3_gasket'],added=[],removed=[]),
                reference_uncertainties=['Visible blue edge lobes motivate shape; lobe count follows existing bolt count, not photo measurement',
                                         'Back symmetry, collars, holes and all dimensions inferred; product/internal mechanism unidentified',
                                         'Only first pipe3 body refined; other blue bodies intentionally retained for comparison'])
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
