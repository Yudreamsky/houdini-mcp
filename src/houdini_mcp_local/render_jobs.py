"""Durable rendering jobs survive the short-lived MCP stdio client."""
import ctypes,hashlib,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
from .io_utils import atomic_json
from .locking import file_lock

ROOT=Path(__file__).resolve().parents[2]
JOBS=ROOT/'evidence'/'render-jobs'
HYTHON=Path(os.environ.get('HOUDINI_HYTHON','C:/Program Files/Side Effects Software/Houdini 20.5.487/bin/hython.exe'))

def process_created(pid):
    if os.name!='nt':return None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:return None
    try:
        times=[ctypes.c_ulonglong() for _ in range(4)]
        ok=kernel.GetProcessTimes(ctypes.c_void_p(handle),*(ctypes.byref(t) for t in times))
        return str(times[0].value) if ok else None
    finally:kernel.CloseHandle(ctypes.c_void_p(handle))


def alive(pid,created=None):
    actual=process_created(pid) if created is not None else None
    if actual is not None and str(created)!=actual:return False
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
    if status['state'] in ('queued','running','cancel_requested') and (folder/'process.json').exists():
        process=json.loads((folder/'process.json').read_text())
        status['process_alive']=alive(process['pid'],process.get('created'))
        if status['process_alive'] is False:
            status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
            if status['state'] in ('queued','running','cancel_requested'):
                status.update(state='interrupted',error='Worker exited without a terminal record; partial files are not completion.')
    if status['state'] in ('queued','running') and (folder/'cancel.json').exists():status['state']='cancel_requested'
    status['job_id']=job_id;status['directory']=str(folder)
    if status['state'] in ('queued','cancel_requested') and (folder/'launch-error.json').exists() and not (folder/'process.json').exists():
        status['state']='launch_unknown'
        status['launch_error']=json.loads((folder/'launch-error.json').read_text())['error']
    return status

def validate_request(hip_path,start_frame,end_frame,width,height,asset_libraries=None):
    hip=Path(hip_path)
    if not hip.is_absolute() or not hip.is_file() or hip.suffix.lower() not in ('.hip','.hiplc','.hipnc'):raise ValueError('Use an existing absolute HIP path')
    if any(type(v) is not int for v in (start_frame,end_frame,width,height)):raise ValueError('Frame and resolution values must be integers')
    if not (1<=end_frame-start_frame+1<=300):raise ValueError('A job must contain 1 to 300 frames')
    if not (128<=width<=1920 and 128<=height<=1080):raise ValueError('Unsupported preview resolution')
    if not HYTHON.is_file():raise FileNotFoundError(HYTHON)
    libraries=[Path(p) for p in (asset_libraries or [])]
    if any(not p.is_absolute() or not p.is_file() or p.suffix.lower() not in ('.hda','.otl','.hdalc','.hdanc') for p in libraries):raise ValueError('Use existing absolute HDA library paths')
    if len({p.name.lower() for p in libraries})!=len(libraries):raise ValueError('HDA snapshot names must be unique')
    return hip,libraries


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_inputs(folder,request):
    if digest(folder/'scene.hip')!=request['scene_sha256']:raise ValueError('HIP snapshot fingerprint changed')
    for item in request.get('libraries',[]):
        path=Path(item['snapshot']).resolve()
        if path.parent!=folder.resolve() or digest(path)!=item['sha256']:raise ValueError('HDA snapshot fingerprint changed')
    for item in request.get('external_dependencies',[]):
        if digest(item['path'])!=item['sha256']:raise ValueError('External dependency fingerprint changed: '+item['path'])


def verified_outputs(folder,request,outputs):
    valid={}
    for item in outputs:
        frame=item.get('frame')
        if type(frame) is not int or not request['start_frame']<=frame<=request['end_frame']:continue
        try:
            for kind in ('png','exr'):
                path=Path(item[kind]['path']).resolve()
                if path.parent!=folder.resolve() or path.stat().st_size==0 or digest(path)!=item[kind]['sha256']:raise ValueError('Output mismatch')
            if not Path(item['png']['path']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG')
            valid[frame]=item
        except (OSError,KeyError,ValueError):continue
    return [valid[f] for f in sorted(valid)]


def _key(request_id,fingerprint):
    if request_id is not None and (not isinstance(request_id,str) or not 1<=len(request_id)<=128):raise ValueError('request_id must contain 1 to 128 characters')
    return 'explicit:'+request_id if request_id is not None else 'content:'+fingerprint


def _index():
    path=JOBS/'requests.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def _existing(key,fingerprint):
    record=_index().get(key)
    if record:
        if record['fingerprint']!=fingerprint:raise ValueError('request_id already belongs to different render inputs')
        folder=job_dir(record['job_id'])
        verify_inputs(folder,json.loads((folder/'request.json').read_text(encoding='utf-8')))
        return dict(get_status(record['job_id']),deduplicated=True)


def _create(request,hip,libraries,key,fingerprint,reuse=None,parent=None):
    active=[p.name for p in JOBS.iterdir() if p.is_dir() and (p/'status.json').exists() and get_status(p.name)['state'] in ('queued','running','cancel_requested','launch_unknown')]
    if len(active)>=2:raise RuntimeError('Two render jobs are already active; inspect or cancel before submitting another')
    identifier=uuid.uuid4().hex;folder=JOBS/identifier;folder.mkdir()
    shutil.copy2(hip,folder/'scene.hip')
    request=dict(request,libraries=[],fingerprint=fingerprint,request_version=3)
    for path,original in libraries:
        dest=folder/path.name;shutil.copy2(path,dest)
        request['libraries'].append(dict(snapshot=str(dest),source=original['source'],sha256=original['sha256']))
    outputs=[]
    for item in reuse or []:
        copied={'frame':item['frame']}
        for kind in ('png','exr'):
            source=Path(item[kind]['path']);dest=folder/source.name;shutil.copy2(source,dest)
            copied[kind]=dict(item[kind],path=str(dest))
        outputs.append(copied)
    request.update(reused_outputs=outputs,parent_job_id=parent)
    verify_inputs(folder,request)
    atomic_json(folder/'request.json',request)
    atomic_json(folder/'status.json',dict(state='queued',completed_frames=len(outputs),total_frames=request['end_frame']-request['start_frame']+1,outputs=outputs,reused_frames=[v['frame'] for v in outputs],parent_job_id=parent,updated_at=time.time()))
    index=_index();index[key]=dict(job_id=identifier,fingerprint=fingerprint);atomic_json(JOBS/'requests.json',index)
    return identifier


def _launch(identifier,launcher):
    folder=job_dir(identifier)
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


def start_job(hip_path,rop_path,start_frame,end_frame,width,height,composite_node,source_cop_node,asset_path,parameters,launcher,asset_libraries=None,request_id=None,preflight=None):
    hip,libraries=validate_request(hip_path,start_frame,end_frame,width,height,asset_libraries)
    request=dict(hip_path=str(hip),scene_sha256=digest(hip),rop_path=rop_path,start_frame=start_frame,end_frame=end_frame,width=width,height=height,composite_node=composite_node,source_cop_node=source_cop_node,asset_path=asset_path,parameters=parameters)
    library_info=[(p,dict(source=str(p),sha256=digest(p))) for p in libraries]
    fingerprint=hashlib.sha256(json.dumps([request,[v for _,v in library_info]],sort_keys=True,allow_nan=False).encode()).hexdigest()
    key=_key(request_id,fingerprint);JOBS.mkdir(parents=True,exist_ok=True)
    with file_lock(JOBS/'.registry.lock'):
        existing=_existing(key,fingerprint)
        if existing:return existing
    if preflight:
        check=preflight(dict(request,asset_libraries=[str(p) for p in libraries]))
        if not check['ready']:raise ValueError('Render preflight failed: '+'; '.join(check['errors']))
        request.update(external_dependencies=check.get('external_dependencies',[]),preflight=check)
    with file_lock(JOBS/'.registry.lock'):
        existing=_existing(key,fingerprint)
        if existing:return existing
        identifier=_create(request,hip,library_info,key,fingerprint)
    return _launch(identifier,launcher)


def cancel_job(job_id):
    state=get_status(job_id)
    if state['state'] not in ('queued','running','cancel_requested','launch_unknown'):return dict(state,cancel_accepted=False)
    atomic_json(job_dir(job_id)/'cancel.json',dict(requested_at=time.time()))
    return dict(get_status(job_id),cancel_accepted=True,cancellation_mode='after_current_frame')


def resume_job(job_id,launcher,request_id=None):
    folder=job_dir(job_id);state=get_status(job_id)
    if state['state'] in ('queued','running','cancel_requested','launch_unknown'):raise ValueError('Cannot resume an active or uncertain job')
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'));verify_inputs(folder,request)
    outputs=verified_outputs(folder,request,state.get('outputs',[]))
    if len(outputs)==request['end_frame']-request['start_frame']+1:return dict(state,all_outputs_verified=True,resume_required=False)
    fingerprint=hashlib.sha256(json.dumps([job_id,request,outputs],sort_keys=True).encode()).hexdigest();key=_key(request_id,fingerprint)
    with file_lock(JOBS/'.registry.lock'):
        existing=_existing(key,fingerprint)
        if existing:return existing
        libraries=[(Path(v['snapshot']),v) for v in request.get('libraries',[])]
        identifier=_create(request,folder/'scene.hip',libraries,key,fingerprint,outputs,job_id)
    return _launch(identifier,launcher)

def launch_worker(identifier,hython_path=None):
    """Called inside the durable Houdini owner, not the ephemeral MCP process."""
    folder=job_dir(identifier)
    executable=Path(hython_path) if hython_path else HYTHON
    if not executable.is_absolute() or not executable.is_file():raise ValueError('Invalid hython executable')
    with file_lock(folder/'.launch.lock'):
        if (folder/'process.json').exists():raise RuntimeError('Job already launched; inspect status instead of retrying')
        env=os.environ.copy();env['HOUDINI_MAXTHREADS']='8';env['WORKAI_HOUDINI_MCP']='0'
        with (folder/'worker.log').open('wb') as log:
            p=subprocess.Popen([str(executable),str(Path(__file__).with_name('render_worker.py')),str(folder)],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        atomic_json(folder/'process.json',dict(pid=p.pid,created=process_created(p.pid)))
    return {'pid':p.pid,'job_id':identifier}
