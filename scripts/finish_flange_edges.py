"""HOM finishing layer for the first pipe3 flange pair; leaves managed HDA locked.

Outer rim edges only. No bolt-hole, sealing-plane or pad edits. Units: metres.
"""
import json,math
import hou

NAMES=('pipe3_flange_left','pipe3_flange_right')
GROUP_CODE='''import hou,json,math
n=hou.pwd();g=n.geometry();g.clear();g.merge(n.inputs()[0].geometry())
p=json.loads(g.attribValue('sample_spec'))['parameters'];d=p['diameter_3']
cy=.044+p['rise_3']+d/2;cz=p['spacing_23'];r=.775*d
width=n.evalParm('bevel_width')
if not 0<width<=min(.003,.03*d):raise hou.NodeError('Visual rim bevel width must be positive and <= min(3mm, 3 percent D)')
group=g.createEdgeGroup('first_flange_outer_rims');count=0
for prim in g.prims():
 if prim.attribValue('name') not in ('pipe3_flange_left','pipe3_flange_right'):continue
 for edge in prim.edges():
  a,b=[q.position() for q in edge.points()]
  if abs(a[0]-b[0])<3e-6 and all(abs(math.hypot(q[1]-cy,q[2]-cz)-r)<3e-6 for q in (a,b)):
   group.add(edge);count+=1
if not count:raise hou.NodeError('No target flange outer rim edges found')
'''

def build(asset_path,width=.0015,source_path=None):
    asset=hou.node(asset_path)
    if asset is None or asset.userData('workai_recipe')!='pipe_rack_isolated' or not asset.matchesCurrentDefinition():
        raise ValueError('Expected locked pipe_rack_isolated managed HDA')
    if type(width) not in (int,float) or not math.isfinite(width) or not 0<width<=min(.003,.03*asset.evalParm('diameter_3')):
        raise ValueError('Visual rim bevel width must be positive and <= min(3mm, 3 percent D)')
    parent=asset.parent();source=hou.node(source_path) if source_path else parent.node('rubber_assignment') or asset
    if source is None or source.parent()!=parent:raise ValueError('Expected a sibling source SOP')
    if parent.node('flange_edges'):raise ValueError('Finishing layer already exists; edit its width instead')
    # Explicit shared base normals keep non-target shading identical in A/B.
    base_normals=parent.createNode('normal','base_vertex_normals');base_normals.setInput(0,source)
    base_normals.parm('type').set(1);base_normals.parm('cuspangle').set(60)
    edges=parent.createNode('python','flange_edges');edges.setInput(0,base_normals)
    edges.addSpareParmTuple(hou.FloatParmTemplate('bevel_width','Outer rim bevel width (m)',1,default_value=(width,),min=0,max=.003,min_is_strict=True,max_is_strict=True))
    edges.parm('python').set(GROUP_CODE)
    bevel=parent.createNode('polybevel::3.0','flange_bevel');bevel.setInput(0,edges)
    bevel.parm('group').set('first_flange_outer_rims');bevel.parm('grouptype').set(2)
    bevel.parm('offset').setExpression('ch("../flange_edges/bevel_width")')
    bevel.parm('divisions').set(3);bevel.parm('filletshape').set(4)
    bevel.parm('useedgefilletgroup').set(1);bevel.parm('edgeprims').set('flange_roundover_faces')
    normal=parent.createNode('normal','flange_vertex_normals');normal.setInput(0,bevel)
    normal.parm('group').set('@name=pipe3_flange_left @name=pipe3_flange_right');normal.parm('grouptype').set(4)
    normal.parm('type').set(1);normal.parm('cuspangle').set(60)
    out=parent.createNode('null','OUT_FINISHED');out.setInput(0,normal);out.setDisplayFlag(True);out.setRenderFlag(True)
    out.cook(force=True)
    for node in (base_normals,edges,bevel,normal,out):
        if node.errors():raise RuntimeError(str(node.errors()))
    parent.layoutChildren()
    return dict(output=out.path(),width_control=edges.path()+'/bevel_width',bevel=bevel.path(),normal=normal.path(),source=source.path(),comparison_source=base_normals.path(),names=list(NAMES),width=width)


def verify(asset_path,output_path):
    from houdini_mcp_local import assembly_checks,rack_inspection,pad_checks
    asset=hou.node(asset_path);out=hou.node(output_path);geo=out.geometry()
    before=assembly_checks.fingerprints(asset.geometry());after=assembly_checks.fingerprints(geo)
    diff=assembly_checks.compare(before,after)
    assert diff['changed']==sorted(NAMES) and len(diff['unchanged'])==210 and not diff['removed'] and not diff['added'],diff
    def untouched_normals(g):
        return [(v.attribValue('name'),tuple(tuple(q.attribValue('N')) for q in v.vertices())) for v in g.prims() if v.attribValue('name') not in NAMES]
    assert untouched_normals(asset.parent().node('base_vertex_normals').geometry())==untouched_normals(geo),'Non-target normals changed'
    check=rack_inspection.inspect(asset,geo);assert check['passed'],check['issues']
    # Face-level invariance outside the narrow outer rim band, including holes.
    p=json.loads(geo.attribValue('sample_spec'))['parameters'];cy=.044+p['rise_3']+p['diameter_3']/2;cz=p['spacing_23'];r=.775*p['diameter_3']
    def protected(g):
        return sorted((v.attribValue('name'),tuple(tuple(q.point().position()) for q in v.vertices())) for v in g.prims() if v.attribValue('name') in NAMES and max(math.hypot(q.point().position()[1]-cy,q.point().position()[2]-cz) for q in v.vertices())<r-.004)
    assert protected(asset.geometry())==protected(geo),'Protected hole/inner faces changed'
    topology={}
    for name in NAMES:
        points=[];faces=[];lookup={}
        for prim in geo.prims():
            if prim.attribValue('name')!=name:continue
            face=[]
            for v in prim.vertices():
                key=v.point().number()
                if key not in lookup:lookup[key]=len(points);points.append(tuple(v.point().position()))
                face.append(lookup[key])
            faces.append(face)
        t=pad_checks.topology(dict(points=points,faces=faces));assert t['closed'] and t['components']==1 and t['signed_volume']>0 and t['euler']==-2*p['bolt_count'],t
        topology[name]=t
    fillets=geo.findPrimGroup('flange_roundover_faces');assert fillets and len(fillets.prims())>0
    assert all(v.attribValue('name') in NAMES for v in fillets.prims())
    assert asset.matchesCurrentDefinition()
    return dict(passed=True,part_diff=diff,inspection=check,topology=topology,fillet_faces=len(fillets.prims()),protected_hole_faces_unchanged=True,non_target_normals_unchanged=True,locked_hda=True,finished_points=len(geo.points()),finished_primitives=len(geo.prims()))
