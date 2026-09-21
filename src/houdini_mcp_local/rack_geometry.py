"""Three parallel pipes sharing each transverse hanger. Illustrative metres.

The compiler embeds the unchanged straight recipe as a private base module.
"""
import math
try:
    base
except NameError:
    from . import sample_geometry as base

PARAMETERS={k:base.PARAMETERS[k] for k in ('length','support_pitch','hanger_height','bolt_count','segments')}
for i,d in enumerate((.32,.25,.20),1):
    PARAMETERS[f'diameter_{i}']=(d,.10,.60,f'Pipe {i} outside diameter (m)')
    PARAMETERS[f'wall_{i}']=(.008,.002,.030,f'Pipe {i} wall (m)')
    PARAMETERS[f'rise_{i}']=((0,.10,.02)[i-1],0,.30,f'Pipe {i} bottom rise above web (m)')
PARAMETERS.update(spacing_12=(.60,.20,1.20,'Pipe 1-2 horizontal center spacing (m)'),
                  spacing_23=(.55,.20,1.20,'Pipe 2-3 horizontal center spacing (m)'))


def validate(values):
    unknown=set(values)-set(PARAMETERS)
    if unknown:raise ValueError('Unknown rack parameters: '+', '.join(sorted(unknown)))
    p={k:v[0] for k,v in PARAMETERS.items()};p.update(values)
    for key,value in p.items():
        _,lo,hi,_=PARAMETERS[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError('Parameter outside finite bounds: '+key)
    for i in (1,2,3):
        base.validate(pipe_parameters(p,i))
        if p['hanger_height']<p[f'diameter_{i}']+p[f'rise_{i}']+.2:
            raise ValueError(f'Hanger height must clear pipe {i} diameter + rise + 0.2 m')
    for a,b in ((1,2),(2,3)):
        if p[f'spacing_{a}{b}']<.775*(p[f'diameter_{a}']+p[f'diameter_{b}'])+.04:
            raise ValueError(f'Horizontal spacing {a}-{b} must clear flange envelopes plus 0.04 m')
    return p


def pipe_parameters(p,i):
    return {k:(p[f'{k}_{i}'] if k in ('diameter','wall') else p[k]) for k in base.PARAMETERS}


def centers(p):
    return [-p['spacing_12'],0,p['spacing_23']]


def web(name,x,low,high,holes):
    """Welded web, explicit leg and hanger holes, regular slots between them."""
    mesh=base.Mesh(name,'channel_web',(.52,.56,.60));width=.0205
    count=max(2,int((high-low)/.06));step=(high-low)/count
    regular=[low+(i+.5)*step for i in range(count)]
    slots=sorted(holes+[z for z in regular if min(abs(z-h) for h in holes)>=.04])
    for k,z in enumerate(slots):
        left=(low if k==0 else (slots[k-1]+z)/2)-z
        right=(high if k==len(slots)-1 else (z+slots[k+1])/2)-z
        angles=sorted(set([i*math.pi/12 for i in range(24)]+[math.atan2(v,u)%(2*math.pi) for u in (left,right) for v in (-width,width)]))
        outside=[];inside=[]
        for a in angles:
            u,v=math.cos(a),math.sin(a)
            scale=min((right if u>=0 else -left)/max(abs(u),1e-15),width/max(abs(v),1e-15))
            outside.append((u*scale,v*scale));inside.append((.012*u,.0045*v))
        omit=[]
        for j,(u,v) in enumerate(outside):
            nxt=outside[(j+1)%len(outside)][0]
            if (k>0 and abs(u-left)<1e-9 and abs(nxt-left)<1e-9) or (k<len(slots)-1 and abs(u-right)<1e-9 and abs(nxt-right)<1e-9):omit.append(j)
        base.plate_with_hole(mesh,outside,inside,.040,.044,lambda y,u,v:(x+v,y,z+u),omit)
    return mesh.data()


def move(part,y=0,z=0):
    part['points']=[[a,b+y,c+z] for a,b,c in part['points']];return part


def build(values):
    p=validate(values);parts=[];zs=centers(p);positions=None;metal=(.48,.52,.57)
    for i,z in enumerate(zs,1):
        pipe=base.build(pipe_parameters(p,i));positions=pipe['support_positions']
        for part in pipe['parts']:
            if part['name'].startswith('support_'):continue
            part['name']=f'pipe{i}_'+part['name']
            if part['kind']=='pipe':part['color']=[(.45,.035,.025),(.07,.08,.09),(.12,.14,.16)][i-1]
            parts.append(move(part,y=p[f'rise_{i}'],z=z))
    low=zs[0]-p['diameter_1']/2-.25;high=zs[-1]+p['diameter_3']/2+.25
    hangers=[low+.045,high-.045]
    holes=hangers+[z+side*(p[f'diameter_{i}']/2+.004) for i,z in enumerate(zs,1) for side in (-1,1)]
    for x in positions:
        index=int(round(abs(x)/p['support_pitch']-.5));name=('rack_neg_' if x<0 else 'rack_pos_')+str(index)
        parts.append(web(name+'_web',x,low,high,holes))
        for side in (-1,1):
            xc=x+side*.0225;z=hangers[0 if side<0 else 1]
            parts.append(base.box(name+f'_lip_{side}','channel_lip',(xc-.002,0,low),(xc+.002,.040,high),metal))
            parts.append(base.tube(name+f'_rod_{side}','hanger',-.012,p['hanger_height'],.004,0,(z,x),metal,16,axis=1))
            parts.append(base.box(name+f'_anchor_{side}','anchor',(x-.045,p['hanger_height'],z-.04),(x+.045,p['hanger_height']+.008,z+.04),metal))
            for y in (.031,.044):
                parts.append(base.tube(name+f'_nut_{side}_{y}','hanger_nut',y,y+.009,.010,.0042,(z,x),metal,6,axis=1))
        for i,z in enumerate(zs,1):
            r=p[f'diameter_{i}']/2;rise=p[f'rise_{i}'];clamp=name+f'_pipe{i}_clamp'
            if rise>0:
                parts.append(base.box(name+f'_pipe{i}_seat','seat',(x-.018,.044,z-.9*r),(x+.018,.044+rise,z+.9*r),metal))
            parts.append(move(base.u_bolt(clamp,x,r,r+.044+rise,int(p['segments'])),z=z))
            for side in (-1,1):
                cz=z+side*(r+.004)
                parts.append(base.tube(clamp+f'_washer_{side}','clamp_washer',.034,.040,.011,.0044,(cz,x),metal,24,axis=1))
                parts.append(base.tube(clamp+f'_nut_{side}','clamp_nut',.022,.034,.010,.0044,(cz,x),metal,6,axis=1))
    return dict(parameters=p,parts=parts,recipe='pipe_rack_sample',units='metres',support_style='shared_u_bolt_v1',
                pipe_centers=[[0,p[f'diameter_{i}']/2+.044+p[f'rise_{i}'],z] for i,z in enumerate(zs,1)],
                support_positions=positions,channel_z_bounds=[low,high],
                dimensions_source='Illustrative values, not measured from photograph',
                simplifications=['Exactly three parallel pipes; common length and support pitch',
                                 'Simplified solid riser seats; no structural or installation certification',
                                 'Local elliptical slot layout and unthreaded 8mm U-bolts are illustrative'])


def cook(node):
    import hou,json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS});geo=node.geometry();geo.clear()
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
