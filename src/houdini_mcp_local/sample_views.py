"""Bounded GUI geometry-review captures with explicit state restoration."""
import base64
import hashlib
import uuid
from pathlib import Path
import hou
from .procedural_assets import managed, ROOT


def capture(path, views, width, height, part_types=None,part_names=None):
    if not hou.isUIAvailable(): raise ValueError('A graphical Houdini session is required')
    if not 1<=len(views)<=4 or len(set(views))!=len(views) or any(v not in ('front','right','top','perspective') for v in views):
        raise ValueError('Select 1-4 unique front/right/top/perspective views')
    if type(width) is not int or type(height) is not int or not (128<=width<=1920 and 128<=height<=1080):
        raise ValueError('Unsupported preview resolution')
    node=managed(path); parent=node.parent(); geo=node.geometry()
    kinds={p.attribValue('part_type') for p in geo.prims()}
    if part_types and not set(part_types)<=kinds: raise ValueError('Unknown part_types filter')
    names={p.attribValue('name') for p in geo.prims()}
    if part_names is not None and (not part_names or len(part_names)>128 or len(set(part_names))!=len(part_names) or not set(part_names)<=names):raise ValueError('Select 1-128 unique existing part_names')
    selected_names=sorted({p.attribValue('name') for p in geo.prims() if (not part_types or p.attribValue('part_type') in part_types) and (part_names is None or p.attribValue('name') in part_names)})
    if not selected_names:raise ValueError('Filters select no parts')
    viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer is None: raise ValueError('No Scene Viewer available')
    viewport=viewer.curViewport(); settings=viewport.settings()
    old_pwd=viewer.pwd(); old_type=viewport.type(); old_camera=viewport.camera(); old_view=viewport.defaultCamera().stash()
    old_lock=viewport.isCameraLockedToView(); old_light=settings.lighting()
    shading=[(settings.displaySet(t),settings.displaySet(t).shadedMode()) for t in (hou.displaySetType.DisplayModel,hou.displaySetType.CurrentModel)]
    old_display=parent.displayNode(); old_render=parent.renderNode()
    selected=list(hou.selectedNodes())
    flags=[(o,o.isDisplayFlagSet()) for o in hou.node('/obj').children() if isinstance(o,hou.ObjNode)]
    guides={g:settings.guideEnabled(g) for g in (hou.viewportGuide.XYPlane,hou.viewportGuide.XZPlane,hou.viewportGuide.YZPlane,hou.viewportGuide.ObjectSelection)}
    folder=ROOT/'evidence'/'asset-views'/uuid.uuid4().hex; folder.mkdir(parents=True)
    temp=None; outputs=[]; view_cameras=[]
    try:
        for obj,_ in flags: obj.setDisplayFlag(obj==parent)
        for obj in selected: obj.setSelected(False)
        target=node
        if part_types or part_names is not None:
            temp=parent.createNode('python','__workai_view_'+uuid.uuid4().hex[:8])
            temp.setInput(0,node)
            temp.parm('python').set('g=hou.pwd().geometry()\ng.deletePrims([p for p in g.prims() if p.attribValue("name") not in '+repr(selected_names)+'],False)')
            temp.setDisplayFlag(True); target=temp
        else: node.setDisplayFlag(True)
        viewer.setPwd(parent)
        viewport.setCamera(None); settings.setLighting(hou.viewportLighting.Headlight)
        for display,_ in shading: display.setShadedMode(hou.glShadingType.Smooth)
        for guide in guides: settings.enableGuide(guide,False)
        bbox=target.geometry().boundingBox()
        for view in views:
            viewport.changeType(getattr(hou.geometryViewportType,view.capitalize()))
            view_cameras.append((viewport.type(),viewport.defaultCamera().stash()))
            if view=='perspective':
                camera=viewport.defaultCamera(); camera.setRotation(hou.hmath.buildRotate((22,-35,0)).extractRotationMatrix3())
                camera.setPerspective(True)
            framing=bbox
            if view=='perspective':
                # Pane framing can crop a long diagonal part in a wide flipbook.
                c=bbox.center();e=bbox.sizevec()*(.5*max(1.,width/height,height/width)*1.15)
                framing=hou.BoundingBox(*(tuple(c-e)+tuple(c+e)))
            viewport.frameBoundingBox(framing)
            if view!='perspective':
                # Flipbook output aspect can differ from the on-screen pane.
                # Fit the projected bounds to the requested image, not pane size.
                axes={'front':(0,1),'right':(2,1),'top':(0,2)}[view]
                size=bbox.sizevec()
                camera=viewport.defaultCamera()
                camera.setOrthoWidth(max(size[axes[0]],size[axes[1]]*width/height)*1.25)
            hou.ui.triggerUpdate()
            output=folder/(view+'.png')
            flip=viewer.flipbookSettings().stash(); flip.frameRange((hou.frame(),hou.frame()))
            flip.outputToMPlay(False); flip.output(str(output)); flip.useResolution(True); flip.resolution((width,height))
            viewer.flipbook(viewport,flip)
            raw=output.read_bytes()
            if not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise RuntimeError('Viewport capture is not a PNG')
            outputs.append(dict(view=view,path=str(output),sha256=hashlib.sha256(raw).hexdigest(),image_base64=base64.b64encode(raw).decode('ascii'),part_types=part_types or sorted(kinds),part_names=selected_names,bounds={'min':list(bbox.minvec()),'max':list(bbox.maxvec())}))
    finally:
        if temp is not None: temp.destroy()
        if old_display: old_display.setDisplayFlag(True)
        if old_render: old_render.setRenderFlag(True)
        for obj,flag in flags: obj.setDisplayFlag(flag)
        viewer.setPwd(old_pwd)
        for typ,cam in reversed(view_cameras):
            viewport.changeType(typ); viewport.setDefaultCamera(cam)
        viewport.changeType(old_type); viewport.setDefaultCamera(old_view); viewport.setCamera(old_camera); viewport.lockCameraToView(old_lock)
        settings.setLighting(old_light)
        for display,mode in shading: display.setShadedMode(mode)
        for guide,value in guides.items(): settings.enableGuide(guide,value)
        # setPwd can implicitly select the object; restore selection last.
        for obj in hou.selectedNodes():obj.setSelected(False)
        for obj in selected:obj.setSelected(True)
    return dict(views=outputs,path=path,restored_display_flags=True,
                note='GUI geometry review, not material acceptance. Temporary visibility/filter operations are restored but may leave the scene marked dirty.')
