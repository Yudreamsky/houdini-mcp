"""Portable, metre-based visual sample. No engineering-standard dimensions implied.

Embedded verbatim in the generated HDA; only Python standard library is required.
"""
import math

PARAMETERS = {
    'length': (2.4, 1.2, 6.0, 'Pipe length (m)'),
    'diameter': (.32, .10, .60, 'Pipe outside diameter (m)'),
    'wall': (.008, .002, .030, 'Pipe wall (m)'),
    'support_pitch': (.90, .40, 2.0, 'Support repeat pitch (m)'),
    'hanger_height': (1.20, .70, 2.50, 'Hanger height (m)'),
    'bolt_count': (8, 6, 16, 'Flange bolt count'),
    'segments': (48, 24, 96, 'Circular segments'),
}


def validate(values):
    unknown = set(values) - set(PARAMETERS)
    if unknown:
        raise ValueError('Unknown sample parameters: ' + ', '.join(sorted(unknown)))
    result = {k: v[0] for k, v in PARAMETERS.items()}
    result.update(values)
    for key, value in result.items():
        _, lo, hi, _ = PARAMETERS[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError('Parameter outside finite bounds: ' + key)
        if key in ('bolt_count', 'segments') and int(value) != value:
            raise ValueError('Integer parameter required: ' + key)
    if result['wall'] >= result['diameter'] * .2:
        raise ValueError('Wall must be less than 20 percent of outside diameter')
    if result['hanger_height'] < result['diameter'] + .2:
        raise ValueError('Hangers must extend above the pipe envelope')
    if result['support_pitch'] > result['length'] - .24:
        raise ValueError('Support pitch leaves no pair of supports inside the pipe ends')
    if result['segments'] % 4:
        raise ValueError('Circular segments must be a multiple of four')
    return result


class Mesh:
    def __init__(self, name, kind, color):
        self.name, self.kind, self.color = name, kind, color
        self.points, self.faces, self.lookup = [], [], {}

    def point(self, p):
        key = tuple(round(v, 10) for v in p)
        if key not in self.lookup:
            self.lookup[key] = len(self.points); self.points.append(list(p))
        return self.lookup[key]

    def face(self, points):
        self.faces.append([self.point(p) for p in points])

    def data(self):
        return dict(name=self.name, kind=self.kind, color=self.color, points=self.points, faces=self.faces)


def plate_with_hole(mesh, outside, inside, lo, hi, convert, omit=()):
    """Extrude a star-shaped polygon annulus; loops have corresponding CCW vertices."""
    n = len(outside)
    for i in range(n):
        j = (i + 1) % n
        o, p = outside[i], outside[j]; a, b = inside[i], inside[j]
        mesh.face([convert(lo, *o), convert(lo, *a), convert(lo, *b), convert(lo, *p)])
        mesh.face([convert(hi, *o), convert(hi, *p), convert(hi, *b), convert(hi, *a)])
        if i not in omit:
            mesh.face([convert(lo, *o), convert(lo, *p), convert(hi, *p), convert(hi, *o)])
        mesh.face([convert(lo, *b), convert(lo, *a), convert(hi, *a), convert(hi, *b)])


def tube(name, kind, lo, hi, outer, inner, center, color, segments=48, axis=0):
    mesh = Mesh(name, kind, color)
    def xyz(t, u, v):
        p = [0., 0., 0.]; p[axis] = t
        p[(axis + 1) % 3] = u + center[0]; p[(axis + 2) % 3] = v + center[1]
        return p
    angles = [2 * math.pi * i / segments for i in range(segments)]
    outer_loop = [(outer * math.cos(a), outer * math.sin(a)) for a in angles]
    if inner > 0:
        plate_with_hole(mesh, outer_loop, [(inner * math.cos(a), inner * math.sin(a)) for a in angles], lo, hi, xyz)
    else:
        mesh.face([xyz(lo, *p) for p in reversed(outer_loop)])
        mesh.face([xyz(hi, *p) for p in outer_loop])
        for i, p in enumerate(outer_loop):
            q = outer_loop[(i + 1) % segments]
            mesh.face([xyz(lo, *p), xyz(lo, *q), xyz(hi, *q), xyz(hi, *p)])
    return mesh.data()


def box(name, kind, minimum, maximum, color):
    mesh = Mesh(name, kind, color)
    points = [[maximum[a] if i & (1 << a) else minimum[a] for a in range(3)] for i in range(8)]
    for face in ((0, 4, 6, 2), (1, 3, 7, 5), (0, 1, 5, 4), (2, 6, 7, 3), (0, 2, 3, 1), (4, 5, 7, 6)):
        mesh.face([points[i] for i in face])
    return mesh.data()


def flange(name, lo, hi, diameter, count, height, segments):
    """Annular flange divided into welded sectors, each with a real bolt hole."""
    mesh = Mesh(name, 'flange', (.10, .28, .50))
    ro, ri, bc, hole = .775 * diameter, .5 * diameter, .635 * diameter, .047 * diameter
    steps = max(6, segments // count)
    for k in range(count):
        angle = 2 * math.pi * k / count
        a, b = angle - math.pi / count, angle + math.pi / count
        center = (bc * math.cos(angle), bc * math.sin(angle))
        boundary = [(ro * math.cos(a + (b-a)*i/steps), ro * math.sin(a + (b-a)*i/steps)) for i in range(steps+1)]
        boundary += [(ri * math.cos(b - (b-a)*i/steps), ri * math.sin(b - (b-a)*i/steps)) for i in range(steps+1)]
        boundary.sort(key=lambda p: math.atan2(p[1]-center[1], p[0]-center[0]))
        inner = []
        for u, v in boundary:
            theta = math.atan2(v-center[1], u-center[0])
            inner.append((center[0]+hole*math.cos(theta), center[1]+hole*math.sin(theta)))
        # Radial interfaces are welded to adjacent sectors; do not leave internal walls.
        omit = []
        for i, p in enumerate(boundary):
            q = boundary[(i+1) % len(boundary)]
            if abs(p[0]*q[1]-p[1]*q[0]) < 1e-10:
                omit.append(i)
        plate_with_hole(mesh, boundary, inner, lo, hi, lambda x,y,z: (x,y+height,z), omit)
    return mesh.data()


def slotted_web(name, x, span):
    """Welded web with true elliptical long holes; visual approximation of punched slots."""
    mesh = Mesh(name, 'channel_web', (.52,.56,.60))
    count = max(2, int(span/.060)); cell = span/count; half = cell/2; width = .0205
    # Add exact rectangle corners so the outer ring does not chamfer the web.
    angles = sorted(set([i*math.pi/12 for i in range(24)] + [math.atan2(v,u) % (2*math.pi) for u in (-half,half) for v in (-width,width)]))
    for k in range(count):
        z = -span/2 + (k+.5)*cell
        outside, inside = [], []
        for a in angles:
            u,v = math.cos(a), math.sin(a)
            scale = min(half/max(abs(u),1e-15), width/max(abs(v),1e-15))
            outside.append((u*scale,v*scale)); inside.append((.012*u,.0045*v))
        omit = []
        for i,(u,v) in enumerate(outside):
            next_u = outside[(i+1)%len(outside)][0]
            if (k > 0 and abs(u+half)<1e-9 and abs(next_u+half)<1e-9) or (k<count-1 and abs(u-half)<1e-9 and abs(next_u-half)<1e-9):
                omit.append(i)
        # x/y/z permutation has positive determinant: extrusion Y, loop (Z,X).
        plate_with_hole(mesh,outside,inside,.040,.044,lambda y,u,v:(x+v,y,z+u),omit)
    return mesh.data(), count, span/2-cell/2


def build(values):
    p = validate(values); d=p['diameter']; length=p['length']; r=d/2
    height=r+.052; gap=.008; thick=d*.11; n=int(p['segments']); bolts=int(p['bolt_count'])
    metal=(.48,.52,.57); pipe=(.45,.035,.025); parts=[]
    parts += [tube('pipe_left','pipe',-length/2,-gap/2,r,r-p['wall'],(height,0),pipe,n),
              tube('pipe_right','pipe',gap/2,length/2,r,r-p['wall'],(height,0),pipe,n)]
    parts += [flange('flange_left',-gap/2-thick,-gap/2,d,bolts,height,n),
              flange('flange_right',gap/2,gap/2+thick,d,bolts,height,n),
              tube('gasket','gasket',-gap/2,gap/2,d*.58,r-p['wall'],(height,0),(.035,.035,.04),n)]
    for i in range(bolts):
        a=2*math.pi*i/bolts; center=(height+d*.635*math.cos(a),d*.635*math.sin(a))
        end=gap/2+thick
        parts += [tube(f'bolt_{i:02}_shaft','bolt',-end-.006,end+.022,d*.032,0,center,metal,16),
                  tube(f'bolt_{i:02}_head','bolt_head',-end-.018,-end-.006,d*.057,0,center,metal,6),
                  tube(f'bolt_{i:02}_washer_left','washer',-end-.006,-end,d*.060,d*.034,center,metal,24),
                  tube(f'bolt_{i:02}_washer_right','washer',end,end+.006,d*.060,d*.034,center,metal,24),
                  tube(f'bolt_{i:02}_nut','nut',end+.006,end+.018,d*.057,d*.034,center,metal,6)]
    span=d+.50; positions=[]; x=p['support_pitch']/2
    while x<=length/2-.12+1e-9:
        positions.extend([-x,x]); x+=p['support_pitch']
    for x in sorted(positions):
        # Name derives from side and repeat index, not unstable sorted enumeration.
        slot=int(round(abs(x)/p['support_pitch']-.5)); prefix=('support_neg_' if x<0 else 'support_pos_')+str(slot)
        web, holes, rod_z=slotted_web(prefix+'_web',x,span); parts.append(web)
        for side in (-1,1):
            xc=x+side*.0225
            parts.append(box(prefix+f'_lip_{side}','channel_lip',(xc-.002,0,-span/2),(xc+.002,.040,span/2),metal))
            z=side*rod_z
            parts.append(tube(prefix+f'_rod_{side}','hanger',-.012,p['hanger_height'],.004,0,(z,x),metal,16,axis=1))
            parts.append(box(prefix+f'_anchor_{side}','anchor',(x-.045,p['hanger_height'],z-.04),(x+.045,p['hanger_height']+.008,z+.04),metal))
            for y in (.031,.044):
                parts.append(tube(prefix+f'_nut_{side}_{y}','hanger_nut',y,y+.009,.010,.0042,(z,x),metal,6,axis=1))
        parts.append(tube(prefix+'_clamp','clamp',x-.014,x+.014,r+.008,r,(height,0),metal,n))
    return {'parameters':p,'parts':parts,'dimensions_source':'illustrative adjustable values, not measured from photograph',
            'support_positions':sorted(positions),'pipe_center_y':height,'flange_outer_diameter':d*1.55,
            'bolt_circle_diameter':d*1.27,'channel_span':span,'units':'metres',
            'simplifications':['ellipse slots approximate punched slots','unthreaded rods and bolts','simplified clamp and anchors','no inferred ceiling or hidden connections']}


def cook(node):
    """HDA PythonModule entry; build geometry without any repository import."""
    import hou, json
    spec=build({k:node.parent().evalParm(k) for k in PARAMETERS})
    geo=node.geometry(); geo.clear()
    name=geo.addAttrib(hou.attribType.Prim,'name','')
    kind=geo.addAttrib(hou.attribType.Prim,'part_type','')
    cd=geo.addAttrib(hou.attribType.Prim,'Cd',(1.,1.,1.))
    for part in spec.pop('parts'):
        points=[]
        for pos in part['points']:
            point=geo.createPoint(); point.setPosition(pos); points.append(point)
        group=geo.createPrimGroup(part['name'].replace('-','m').replace('.','_'))
        for indices in part['faces']:
            face=geo.createPolygon()
            for index in indices: face.addVertex(points[index])
            face.setAttribValue(name,part['name']); face.setAttribValue(kind,part['kind']); face.setAttribValue(cd,part['color']); group.add(face)
    geo.addAttrib(hou.attribType.Global,'sample_spec','')
    geo.setGlobalAttribValue('sample_spec',json.dumps(spec,sort_keys=True))
