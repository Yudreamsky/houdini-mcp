"""Standalone S1 visual study, not a managed MCP recipe or structural specification.

Metres; a continuous folded C section with actual capsule slots. Pure Python
geometry is embedded in the delivered HIP so it does not require this checkout.
"""
import math

DEFAULTS = dict(length=1.05, width=.041, depth=.041, thickness=.0025,
                lip=.008, pitch=.060, slot_length=.026, slot_width=.011)


def validate(values):
    if set(values)-set(DEFAULTS):
        raise ValueError('Unknown channel parameter')
    p = dict(DEFAULTS, **values)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in p.values()):
        raise ValueError('Parameters must be positive finite numbers')
    if not .15 <= p['length'] <= 3 or not .025 <= p['width'] <= .10 or not .025 <= p['depth'] <= .10:
        raise ValueError('Outside visual sample envelope')
    w,h,t,lip = (p[k] for k in ('width','depth','thickness','lip'))
    if t > min(w,h)*.12 or not 2*t < lip < w/2-t:
        raise ValueError('Invalid wall/lip/opening proportions')
    if not 2*t < p['slot_width'] < w-4*t or not p['slot_width'] < p['slot_length'] < p['pitch']-4*t:
        raise ValueError('Slot overlaps edge or neighbouring slot')
    if p['pitch'] > p['length']/2:
        raise ValueError('At least two slots required')
    return p


class Mesh:
    def __init__(self):
        self.points=[]; self.faces=[]; self.lookup={}

    def face(self, coords):
        face=[]
        for p in coords:
            key=tuple(round(v,10) for v in p)
            if key not in self.lookup:
                self.lookup[key]=len(self.points); self.points.append(list(key))
            face.append(self.lookup[key])
        self.faces.append(face)


def build(values=None):
    p=validate(values or {});m=Mesh()
    L,w,h,t,lip,pitch,sl,sw=(p[k] for k in DEFAULTS)
    # Centre equal-pitch holes; put the extra length in the unperforated ends.
    count=int((L-sl-2*t)//pitch)+1
    centers=[(i-(count-1)/2)*pitch for i in range(count)]
    a=w/2-t;r=sw/2;straight=(sl-sw)/2
    # Right-hand section arc from the outer top to the inner top. Small
    # manufactured bends are a visual assumption, not a standard profile.
    profile=[(a,h),(w/2-.3*t,h),(w/2,h-.3*t),(w/2,.3*t),
             (w/2-.3*t,0),(w/2-lip,0),(w/2-lip,t),(a,t),(a,h-t)]
    side_stations=set()
    def xyz(y,u,v,z):return (v,y,z+u)  # positive cyclic orientation
    for k,z in enumerate(centers):
        lo=(-L/2 if k==0 else z-pitch/2)-z
        hi=(L/2 if k==count-1 else z+pitch/2)-z
        angles=[i*math.pi/24 for i in range(48)]
        angles += [math.atan2(v,u)%(2*math.pi) for u in (lo,hi) for v in (-a,a)]
        # Include every capsule-to-straight tangent and exact rectangle corner.
        angles += [math.atan2(v,u)%(2*math.pi) for u in (-straight,straight) for v in (-r,r)]
        angles=sorted(set(round(v,12) for v in angles))
        outer=[];inner=[]
        for theta in angles:
            u,v=math.cos(theta),math.sin(theta)
            scale=min((hi if u>=0 else -lo)/max(abs(u),1e-15),a/max(abs(v),1e-15))
            q=(u*scale,v*scale);outer.append(q)
            # Ray / capsule: central straight segment or semicircular cap.
            sy=r/max(abs(v),1e-15)
            if abs(u*sy)<=straight:rad=sy
            else:
                dot=straight*abs(u)
                rad=dot+math.sqrt(max(0,dot*dot-straight*straight+r*r))
            inner.append((u*rad,v*rad))
        for i,o in enumerate(outer):
            j=(i+1)%len(outer);q=outer[j];b,c=inner[i],inner[j]
            m.face([xyz(h-t,*o,z),xyz(h-t,*b,z),xyz(h-t,*c,z),xyz(h-t,*q,z)])
            m.face([xyz(h,*o,z),xyz(h,*q,z),xyz(h,*c,z),xyz(h,*b,z)])
            m.face([xyz(h-t,*c,z),xyz(h-t,*b,z),xyz(h,*b,z),xyz(h,*c,z)])
            at_side=abs(abs(o[1])-a)<1e-8 and abs(o[1]-q[1])<1e-8
            if at_side:
                side_stations.update((round(z+o[0],10),round(z+q[0],10)))
            else:
                end=(k==0 and abs(o[0]-lo)<1e-8 and abs(q[0]-lo)<1e-8) or (k==count-1 and abs(o[0]-hi)<1e-8 and abs(q[0]-hi)<1e-8)
                if end:m.face([xyz(h-t,*o,z),xyz(h-t,*q,z),xyz(h,*q,z),xyz(h,*o,z)])
    stations=sorted(side_stations)
    for side in (-1,1):
        section=[(side*x,y) for x,y in profile]
        if side<0:section.reverse()
        # profile clockwise viewed from +Z; reverse to CCW for positive volume.
        area=sum(x*v-u*y for (x,y),(u,v) in zip(section,section[1:]+section[:1]))
        if area<0:section.reverse()
        m.face([(x,y,-L/2) for x,y in reversed(section)])
        m.face([(x,y,L/2) for x,y in section])
        for (x,y),(u,v) in zip(section,section[1:]+section[:1]):
            if abs(abs(x)-a)<1e-9 and abs(abs(u)-a)<1e-9 and {round(y,10),round(v,10)}=={round(h,10),round(h-t,10)}:
                continue  # welded web interface, no internal wall
            for z0,z1 in zip(stations,stations[1:]):
                m.face([(x,y,z0),(u,v,z0),(u,v,z1),(x,y,z1)])
    return dict(name='S1_slotted_channel',kind='slotted_channel',color=(.48,.52,.57),
                points=m.points,faces=m.faces,parameters=p,slot_centers=centers,
                source='Photo S1; section, dimensions, open side and placement inferred; no hidden connection')


def cook(node):
    import hou,json
    p={k:node.evalParm(k) for k in DEFAULTS};data=build(p);g=node.geometry();g.clear()
    pts=[]
    for pos in data.pop('points'):
        q=g.createPoint();q.setPosition(pos);pts.append(q)
    name=g.addAttrib(hou.attribType.Prim,'name',data['name'])
    kind=g.addAttrib(hou.attribType.Prim,'part_type',data['kind'])
    cd=g.addAttrib(hou.attribType.Prim,'Cd',data['color'])
    for face in data.pop('faces'):
        prim=g.createPolygon()
        for i in face:prim.addVertex(pts[i])
        prim.setAttribValue(name,data['name']);prim.setAttribValue(kind,data['kind']);prim.setAttribValue(cd,data['color'])
    g.addAttrib(hou.attribType.Global,'channel_spec','');g.setGlobalAttribValue('channel_spec',json.dumps(data,sort_keys=True))
