"""Photo-guided visual rack; embedded base and rack modules are supplied by compiler.

Dimensions/back faces are inferred. This is not a manufacturer-specific fitting.
"""
try:
    rack
except NameError:
    from . import rack_geometry as rack
base=rack.base
PARAMETERS=dict(rack.PARAMETERS)
for key,value in dict(length=2.8,support_pitch=1.2,diameter_2=.28,diameter_3=.28,
                      spacing_12=.52,spacing_23=.50,rise_1=0,rise_2=0,rise_3=0).items():
    old=PARAMETERS[key];PARAMETERS[key]=(value,*old[1:])
for i,value in enumerate((.22,-.12,.12),1):
    PARAMETERS[f'joint_offset_{i}']=(value,-.3,.3,f'Pipe {i} joint X offset (m)')


def validate(values):
    import math
    unknown=set(values)-set(PARAMETERS)
    if unknown:raise ValueError('Unknown photo rack parameters: '+', '.join(sorted(unknown)))
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    for key,v in p.items():
        if type(v) not in (int,float) or not math.isfinite(v) or not PARAMETERS[key][1]<=v<=PARAMETERS[key][2]:
            raise ValueError('Parameter outside finite bounds: '+key)
    rack.validate({k:p[k] for k in rack.PARAMETERS})
    positions=[];x=p['support_pitch']/2
    while x<=p['length']/2-.12+1e-9:positions.extend((-x,x));x+=p['support_pitch']
    for i in (1,2,3):
        reach=.044+p[f'diameter_{i}']*.11+.025
        if any(abs(p[f'joint_offset_{i}']-x)<reach+.025 for x in positions):
            raise ValueError(f'Joint {i} overlaps a support station; change offset or support pitch')
    return p


def folded_side(name,x,side,low,high):
    # Small chamfers at the outer fold, return lip around the open underside.
    profile=[(.0205,.040),(.0245,.040),(.0245,.003),(.0215,0),(.0125,0),(.0125,.004),(.0195,.004),(.0205,.005)]
    poly=[(x+side*a,b) for a,b in profile]
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))
    if area<0:poly.reverse()
    m=base.Mesh(name,'channel_lip',(.52,.56,.60))
    m.face([(a,b,low) for a,b in reversed(poly)]);m.face([(a,b,high) for a,b in poly])
    for a,b in zip(poly,poly[1:]+poly[:1]):m.face([(a[0],a[1],low),(b[0],b[1],low),(b[0],b[1],high),(a[0],a[1],high)])
    return m.data()


def build(values):
    p=validate(values);spec=rack.build({k:p[k] for k in rack.PARAMETERS});parts=spec['parts'];zs=rack.centers(p)
    for index,part in enumerate(parts):
        name=part['name'];kind=part['kind']
        if kind=='channel_lip':
            x=(min(q[0] for q in part['points'])+max(q[0] for q in part['points']))/2
            side=-1 if name.endswith('_-1') else 1;x-=side*.0225
            parts[index]=folded_side(name,x,side,*spec['channel_z_bounds']);continue
        if not name.startswith(('pipe1_','pipe2_','pipe3_')):continue
        i=int(name[4]);offset=p[f'joint_offset_{i}'];d=p[f'diameter_{i}'];z=zs[i-1];h=d/2+.044+p[f'rise_{i}']
        if kind=='pipe':
            # Preserve outer endpoints; move only the end against the joint.
            for q in part['points']:
                if abs(abs(q[0])-.004)<1e-8:q[0]=offset+(.044 if q[0]>0 else -.044)
        elif kind=='gasket':
            parts[index]=base.tube(name,kind,offset-.044,offset+.044,d*.60,d/2-p[f'wall_{i}'],(h,z),(.018,.20,.48),int(p['segments']))
        else:
            for q in part['points']:q[0]+=offset+(.04 if q[0]>0 else -.04)
            if kind=='flange':part['color']=(.46,.49,.52)
    spec.update(parameters=p,recipe='pipe_rack_reference',channel_profile='folded_return_v1',
                reference_scope='Foreground three-pipe support/joint visual study; not the full ceiling scene',
                joint_style='thick blue body between two steel flanges; inferred visual envelope, no product identification',
                reference_uncertainties=['Scale, channel section and hidden faces inferred from one oblique image',
                                         'Default pipe bottoms coplanar; prior solid riser seats not evidenced in photo',
                                         'Red pipe fitting still uses the visual flanged template; orange grooved fitting not reconstructed',
                                         'Extra repeated joints, vertical slotted frames, ducts and ceiling are not included'],
                simplifications=spec['simplifications']+['Fold chamfers are illustrative; no thread detail','Blue body internal fitting function is unspecified'])
    return spec


def cook(node):
    # Same standalone polygon writer, bound to this module's build and parameters.
    import hou,json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS});g=node.geometry();g.clear()
    name=g.addAttrib(hou.attribType.Prim,'name','');kind=g.addAttrib(hou.attribType.Prim,'part_type','');cd=g.addAttrib(hou.attribType.Prim,'Cd',(1.,1.,1.))
    for part in spec.pop('parts'):
        pts=[]
        for pos in part['points']:
            pt=g.createPoint();pt.setPosition(pos);pts.append(pt)
        group=g.createPrimGroup(part['name'].replace('-','m').replace('.','_'))
        for ids in part['faces']:
            prim=g.createPolygon()
            for i in ids:prim.addVertex(pts[i])
            prim.setAttribValue(name,part['name']);prim.setAttribValue(kind,part['kind']);prim.setAttribValue(cd,part['color']);group.add(prim)
    g.addAttrib(hou.attribType.Global,'sample_spec','');g.setGlobalAttribValue('sample_spec',json.dumps(spec,sort_keys=True))
