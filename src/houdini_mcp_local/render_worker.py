"""Hython render worker. Completion requires foreground render and output validation."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import hou

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from houdini_mcp_local.asset_ops import set_parameters
from houdini_mcp_local.io_utils import atomic_json

folder=Path(sys.argv[1]);request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
state={'state':'running','completed_frames':0,'total_frames':request['end_frame']-request['start_frame']+1,'outputs':[],'started_at':time.time()}
def status():
    state['updated_at']=time.time()
    atomic_json(folder/'status.json',state)
def info(path):
    raw=path.read_bytes()
    if not raw:raise RuntimeError('Empty render output: '+str(path))
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
try:
    status()
    for library in request.get('libraries',[]):hou.hda.installFile(library['snapshot'])
    try:
        hou.hipFile.load((folder/'scene.hip').as_posix(),suppress_save_prompt=True)
    except hou.LoadWarning as warning:
        state['load_warning']=str(warning)
        if 'incomplete asset' in str(warning).lower() or 'full definition not found' in str(warning).lower():raise
    hou.putenv('HIP',str(Path(request['hip_path']).parent).replace('\\','/'))
    # Freeze the definitions used by this loaded scene before rendering.
    defs={}
    for node in hou.node('/obj').allSubChildren():
        d=node.type().definition()
        if d and d.nodeTypeName().startswith('workai::') and d.nodeTypeName() not in defs:
            dest=folder/('asset-'+str(len(defs))+'.hda');d.copyToHDAFile(dest.as_posix());hou.hda.installFile(dest.as_posix())
            hou.hda.definitionsInFile(dest.as_posix())[0].setIsPreferred(True);defs[d.nodeTypeName()]=info(dest)
    state['definitions']=defs
    if request['parameters']:state['applied']=set_parameters(request['asset_path'],request['parameters'])
    if request['asset_path']:
        asset=hou.node(request['asset_path'])
        if asset is None or asset.geometry() is None or asset.errors():raise RuntimeError('Asset failed to cook')
    r=hou.node(request['rop_path'])
    if r is None or r.type().name()!='ifd':raise ValueError('This renderer supports a Mantra ifd ROP')
    comp=hou.node(request['composite_node']);source=hou.node(request['source_cop_node'])
    if not isinstance(comp,hou.Cop2Node) or not isinstance(source,hou.Cop2Node):raise ValueError('Expected existing COP2 output and source nodes')
    r.parm('soho_foreground').set(1);r.parm('soho_outputmode').set(0)
    r.parm('override_camerares').set(1);r.parm('res_fraction').set('specific')
    r.parmTuple('res_override').set((request['width'],request['height']))
    # Explicit thread cap also applies to the child Mantra process.
    r.parm('soho_pipecmd').set('mantra -j 8')
    state['fps']=hou.fps();status()
    for frame in range(request['start_frame'],request['end_frame']+1):
        state['current_frame']=frame;status();hou.setFrame(frame)
        exr=folder/f'raw_{frame:04}.exr';png=folder/f'frame_{frame:04}.png'
        r.parm('vm_picture').set(exr.as_posix());r.render(frame_range=(frame,frame))
        raw_info=info(exr)
        source.parm('filename1').set(exr.as_posix());source.parm('singleimage').set(1);source.parm('reload').pressButton()
        comp.saveImage(png.as_posix(),(frame,frame))
        image_info=info(png)
        if not png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Invalid PNG signature')
        state['outputs'].append({'frame':frame,'png':image_info,'exr':raw_info})
        state['completed_frames']+=1;status()
    state['state']='completed';state['finished_at']=time.time();status()
except BaseException:
    state['state']='failed';state['error']=traceback.format_exc();state['finished_at']=time.time();status();raise
