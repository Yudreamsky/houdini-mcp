"""Durable rendering jobs survive the short-lived MCP stdio client."""
import ctypes,hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
JOBS=ROOT/'evidence'/'render-jobs'
HYTHON=Path(os.environ.get('HOUDINI_HYTHON','C:/Program Files/Side Effects Software/Houdini 20.5.487/bin/hython.exe'))

def alive(pid):
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,int(pid))
        if not handle:return False if ctypes.get_last_error()==87 else None
        try:
            code=ctypes.c_ulong();ok=kernel.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code))
            return code.value==259 if ok else None
        finally:kernel.CloseHandle(ctypes.c_void_p(handle))
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return None

def job_dir(job_id):
    if len(job_id)!=32 or any(c not in '0123456789abcdef' for c in job_id):raise ValueError('Invalid job id')
    return JOBS/job_id

def get_status(job_id):
    folder=job_dir(job_id);status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
    if status['state'] in ('queued','running') and (folder/'process.json').exists():
        pid=json.loads((folder/'process.json').read_text())['pid']
        status['process_alive']=alive(pid)
        if status['process_alive'] is False:
            status.update(state='interrupted',error='Worker exited without a completed/failed record; partial files are not completion.')
    status['job_id']=job_id;status['directory']=str(folder)
    if status['state']=='queued' and (folder/'launch-error.json').exists():
        status['state']='launch_unknown'
        status['launch_error']=json.loads((folder/'launch-error.json').read_text())['error']
    return status

def start_job(hip_path,rop_path,start_frame,end_frame,width,height,composite_node,source_cop_node,asset_path,parameters,launcher,asset_libraries=None):
    hip=Path(hip_path)
    if not hip.is_absolute() or not hip.is_file() or hip.suffix.lower() not in ('.hip','.hiplc','.hipnc'):raise ValueError('Use an existing absolute HIP path')
    if not (1<=end_frame-start_frame+1<=300):raise ValueError('A job must contain 1 to 300 frames')
    if not (128<=width<=1920 and 128<=height<=1080):raise ValueError('Unsupported preview resolution')
    if not HYTHON.is_file():raise FileNotFoundError(HYTHON)
    libraries=[Path(p) for p in (asset_libraries or [])]
    if any(not p.is_absolute() or not p.is_file() or p.suffix.lower() not in ('.hda','.otl','.hdalc','.hdanc') for p in libraries):raise ValueError('Use existing absolute HDA library paths')
    if len({p.name.lower() for p in libraries})!=len(libraries):raise ValueError('HDA snapshot names must be unique')
    JOBS.mkdir(exist_ok=True,parents=True)
    identifier=uuid.uuid4().hex;folder=JOBS/identifier;folder.mkdir()
    raw=hip.read_bytes();(folder/'scene.hip').write_bytes(raw)
    request={'hip_path':str(hip),'scene_sha256':hashlib.sha256(raw).hexdigest(),'rop_path':rop_path,'start_frame':start_frame,'end_frame':end_frame,'width':width,'height':height,'composite_node':composite_node,'source_cop_node':source_cop_node,'asset_path':asset_path,'parameters':parameters}
    request['libraries']=[]
    for i,p in enumerate(libraries):
        data=p.read_bytes();dest=folder/p.name;dest.write_bytes(data)
        request['libraries'].append({'snapshot':str(dest),'source':str(p),'sha256':hashlib.sha256(data).hexdigest()})
    (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
    (folder/'status.json').write_text(json.dumps({'state':'queued','completed_frames':0,'total_frames':end_frame-start_frame+1,'updated_at':time.time()}))
    try:
        launcher(identifier)
    except Exception as exc:
        # A timed-out bridge call may already have launched the worker. Never
        # overwrite a worker's progress with an invented terminal failure.
        (folder/'launch-error.json').write_text(json.dumps({'error':repr(exc)}))
        result=get_status(identifier)
        if result['state']=='queued':result['state']='launch_unknown'
        result['launch_error']=repr(exc)
        return result
    return get_status(identifier)

def launch_worker(identifier,hython_path=None):
    """Called inside the durable Houdini owner, not the ephemeral MCP process."""
    folder=job_dir(identifier)
    executable=Path(hython_path) if hython_path else HYTHON
    if not executable.is_absolute() or not executable.is_file():raise ValueError('Invalid hython executable')
    if (folder/'process.json').exists():raise RuntimeError('Job already launched; inspect status instead of retrying')
    env=os.environ.copy();env['HOUDINI_MAXTHREADS']='8';env['WORKAI_HOUDINI_MCP']='0'
    with (folder/'worker.log').open('wb') as log:
        p=subprocess.Popen([str(executable),str(Path(__file__).with_name('render_worker.py')),str(folder)],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (folder/'process.json').write_text(json.dumps({'pid':p.pid}))
    return {'pid':p.pid,'job_id':identifier}
