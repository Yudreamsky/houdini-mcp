"""Persistent hython owner: snapshot loading, rendering, compositing and evidence."""
import hashlib
import json
import os
import subprocess
import struct
import sys
import time
import threading
import traceback
from pathlib import Path
import hou

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from houdini_mcp_local.asset_ops import set_parameters
from houdini_mcp_local.io_utils import atomic_json
from houdini_mcp_local.render_jobs import verify_inputs, verified_outputs, process_created
from houdini_mcp_local.render_options import device_evidence, cancellation_receipt
from houdini_mcp_local.image_inspection import inspect_pixels
from houdini_mcp_local import render_controls, render_diagnostics

folder = Path(sys.argv[1])
request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
renderer = request.get('renderer', 'mantra')
started = time.perf_counter()
child = None
state = dict(state='running', renderer=renderer, quality=request.get('quality', 'scene'),
             completed_frames=0, total_frames=request['end_frame'] - request['start_frame'] + 1,
             outputs=[], parent_job_id=request.get('parent_job_id'), reused_frames=[],
             started_at=time.time(), timings={'load_seconds': 0, 'export_seconds': 0,
                                             'composite_seconds': 0, 'inspection_seconds': 0})


class Cancelled(Exception):
    pass


def status():
    state['updated_at'] = time.time()
    state['timings']['worker_elapsed_seconds'] = time.perf_counter() - started
    state['visual_summary'] = {'warning_frames': [v['frame'] for v in state['outputs'] if v.get('visual_check', {}).get('warnings')],
                               'note': 'Rendered output is not artistic acceptance. Black-frame warnings do not fail the job.'}
    atomic_json(folder / 'status.json', state)


def cancellation_point():
    if (folder / 'cancel.json').exists():
        raise Cancelled()


def info(path):
    raw = path.read_bytes()
    if not raw:
        raise RuntimeError('Empty render output: ' + str(path))
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def finish_frame(frame, timings, gpu=None):
    hou.setFrame(frame)
    exr = folder / f'raw_{frame:04}.exr'
    png = folder / f'frame_{frame:04}.png'
    raw_info = info(exr)
    source.parm('filename1').set(exr.as_posix())
    source.parm('singleimage').set(1); source.parm('reload').pressButton()
    t = time.perf_counter()
    comp.saveImage(png.as_posix(), (frame, frame))
    timings['composite_seconds'] = time.perf_counter() - t
    image_info = info(png)
    png_header = png.read_bytes()[:24]
    if not png_header.startswith(b'\x89PNG\r\n\x1a\n') or struct.unpack('>II', png_header[16:24]) != (request['width'], request['height']):
        raise RuntimeError('Invalid PNG or unexpected preview dimensions')
    t = time.perf_counter()
    raw_check = inspect_pixels(source.allPixels('C'), source.allPixels('A'))
    preview_check = inspect_pixels(comp.allPixels('C'), comp.allPixels('A'))
    if not raw_check['finite'] or not preview_check['finite']:
        raise RuntimeError('Nonfinite render/composite pixels')
    timings['inspection_seconds'] = time.perf_counter() - t
    visual = {'raw': raw_check, 'preview': preview_check,
              'warnings': sorted(set(raw_check['warnings'] + preview_check['warnings'])),
              'width': request['width'], 'height': request['height']}
    output = dict(frame=frame, png=image_info, exr=raw_info, timings=timings, visual_check=visual)
    output['effective_settings'] = state.get('effective_settings')
    output['region'] = request.get('region')
    t = time.perf_counter()
    output['diagnostics'] = render_diagnostics.postprocess(folder, frame, request, source, comp)
    timings['diagnostics_seconds'] = time.perf_counter() - t
    if gpu is not None:
        output['gpu_evidence'] = gpu
    state['outputs'].append(output)
    state['outputs'].sort(key=lambda v: v['frame'])
    state['completed_frames'] = len(state['outputs'])
    state['timings']['composite_seconds'] += timings['composite_seconds']
    state['timings']['inspection_seconds'] += timings['inspection_seconds']
    status()


try:
    atomic_json(folder / 'worker-owner.json', {'pid': os.getpid(), 'created': process_created(os.getpid())})
    status(); verify_inputs(folder, request)
    state['outputs'] = verified_outputs(folder, request, request.get('reused_outputs', []))
    state['completed_frames'] = len(state['outputs'])
    state['reused_frames'] = [v['frame'] for v in state['outputs']]
    cancellation_point()
    for library in request.get('libraries', []):
        hou.hda.installFile(library['snapshot'])
        for definition in hou.hda.definitionsInFile(library['snapshot']):
            definition.setIsPreferred(True)
    try:
        hou.hipFile.load((folder / 'scene.hip').as_posix(), suppress_save_prompt=True)
    except hou.LoadWarning as warning:
        state['load_warning'] = str(warning)
        if 'incomplete asset' in str(warning).lower() or 'full definition not found' in str(warning).lower():
            raise
    expected_version = request.get('preflight', {}).get('scene', {}).get('houdini_version')
    if expected_version and expected_version != hou.applicationVersionString():
        raise RuntimeError('Worker Houdini version differs from preflight session')
    hou.putenv('HIP', str(Path(request['hip_path']).parent).replace('\\', '/'))
    for library in request.get('libraries', []):
        hou.hda.installFile(library['snapshot'])
        for definition in hou.hda.definitionsInFile(library['snapshot']):
            definition.setIsPreferred(True)
    if request['parameters']:
        state['applied'] = set_parameters(request['asset_path'], request['parameters'])
    if request['asset_path']:
        asset = hou.node(request['asset_path'])
        if asset is None or asset.geometry() is None or asset.errors():
            raise RuntimeError('Asset failed to cook')
    rop = hou.node(request['rop_path'])
    comp = hou.node(request['composite_node']); source = hou.node(request['source_cop_node'])
    if rop is None or rop.type().name() != 'ifd':
        raise ValueError('Expected a Mantra ifd ROP as render/camera configuration')
    if not isinstance(comp, hou.Cop2Node) or not isinstance(source, hou.Cop2Node):
        raise ValueError('Expected COP2 output and source nodes')
    state['fps'] = hou.fps()
    state['timings']['load_seconds'] = time.perf_counter() - started
    pending = [f for f in range(request['start_frame'], request['end_frame'] + 1) if f not in state['reused_frames']]
    if renderer == 'mantra':
        rop.parm('soho_foreground').set(1); rop.parm('soho_outputmode').set(0)
        rop.parm('override_camerares').set(1); rop.parm('res_fraction').set('specific')
        rop.parmTuple('res_override').set((request['width'], request['height']))
        rop.parm('soho_pipecmd').set('mantra -j 8')
        state['aov_configuration'] = render_diagnostics.configure_mantra(rop, request.get('diagnostics'))
        state['timing_scope'] = 'Mantra render_call includes IFD export, process startup and rendering; these components are not separately measured.'
        for frame in pending:
            cancellation_point(); state['current_frame'] = frame; status(); hou.setFrame(frame)
            state['effective_settings'] = render_controls.configure_mantra(rop, request)
            state['effective_settings']['region'] = render_controls.configure_mantra_region(hou.node(rop.evalParm('camera')), request)
            atomic_json(folder / f'effective_{frame:04}.json', state['effective_settings'])
            rop.parm('vm_picture').set((folder / f'raw_{frame:04}.exr').as_posix())
            t = time.perf_counter(); rop.render(frame_range=(frame, frame))
            finish_frame(frame, {'render_call_seconds': time.perf_counter() - t})
    elif renderer == 'karma_xpu' and pending:
        if request.get('xpu_surface') is not None:
            from houdini_mcp_local.xpu_surface_adapter import export_surface as export_map
        else:
            from houdini_mcp_local.xpu_adapter import export_map
        state['phase'] = 'exporting_usd'; status()
        t = time.perf_counter(); usd = export_map(folder, request, pending, cancellation_point)
        state['effective_settings'] = {'effective': {'pixel_samples': request.get('pixel_samples', 16)},
                                       'source': 'husk command -p; command is recorded',
                                       'region': render_controls.configure_usd_region(usd, request)}
        state['aov_configuration'] = render_diagnostics.configure_usd(usd, request)
        state['timings']['export_seconds'] = time.perf_counter() - t
        state['usd_snapshot'] = info(usd)
        cancellation_point()
        husk = Path(hou.expandString('$HFS')) / 'bin' / ('husk.exe' if os.name == 'nt' else 'husk')
        module_dir = Path(__file__).resolve().parent
        command = [str(husk), '--engine', 'xpu', '--headlight', 'none', '--disable-motionblur', '--ocio', '0',
                   '-j', '8', '-p', str(request.get('pixel_samples', 16)), '--frame-list', *map(str, pending),
                   '-V', '5', '-s', '/Render/Settings', '-o', str(folder / 'raw_$F4.exr'),
                   '--preframe-script', '"' + (module_dir / 'husk_preframe.py').as_posix() + '"',
                   '--postframe-script', '"' + (module_dir / 'husk_postframe.py').as_posix() + '"', str(usd)]
        env = os.environ.copy()
        env.update(KARMA_XPU_DISABLE_EMBREE_DEVICE='1', WORKAI_RENDER_JOB=str(folder), WORKAI_RENDER_SOURCE=str(module_dir.parent))
        atomic_json(folder / 'renderer-command.json', {'command': command, 'gpu_only': True})
        render_started = time.perf_counter()
        with (folder / 'husk.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            renderer_ended = []
            def observe_exit():
                child.wait()
                renderer_ended.append(time.perf_counter())
            observer = threading.Thread(target=observe_exit, daemon=True)
            observer.start()
            atomic_json(folder / 'renderer-process.json', {'pid': child.pid, 'created': process_created(child.pid)})
            state['phase'] = 'rendering'; status()
            handled = set()
            while True:
                for frame in pending:
                    receipt = folder / f'ready_{frame:04}.json'
                    if frame in handled or not receipt.exists():
                        continue
                    completed = json.loads(receipt.read_text())['at']
                    began = json.loads((folder / f'start_{frame:04}.json').read_text())['at']
                    if 'renderer_startup_seconds' not in state['timings']:
                        state['timings']['renderer_startup_seconds'] = began - render_started
                    gpu = device_evidence((folder / 'husk.log').read_text(encoding='utf-8', errors='replace'), frame)
                    if not gpu['verified']:
                        raise RuntimeError('No completed-frame OptiX contribution evidence for frame ' + str(frame))
                    state['current_frame'] = frame
                    finish_frame(frame, {'renderer_frame_seconds': completed - began}, gpu)
                    handled.add(frame)
                if child.poll() is not None:
                    # Final receipt may have appeared between the scan and process exit.
                    if any(f not in handled and (folder / f'ready_{f:04}.json').exists() for f in pending):
                        continue
                    break
                time.sleep(.05)
            observer.join()
            state['timings']['renderer_process_seconds'] = renderer_ended[0] - render_started
            state['renderer_exit_code'] = child.returncode
            # Houdini 20.5 aborts the batch with exit 1 on a pre-frame exception;
            # newer husk versions recognize SkipFrame. Only accept our explicit
            # stop receipt after every started frame has a completed receipt.
            cooperative_stop = cancellation_receipt(folder, pending)
            if cooperative_stop:
                state['renderer_stop'] = cooperative_stop
            if child.returncode and not (child.returncode == 1 and cooperative_stop):
                raise RuntimeError('Karma husk failed; see husk.log (exit ' + str(child.returncode) + ')')
        state['timing_scope'] = 'XPU startup is process launch to first pre-frame hook; frame time is pre-frame to saved-image post-frame hook. Frame time includes scene updates/compilation. Compositing can overlap rendering; do not sum timings as total wall time.'
    elif renderer != 'karma_xpu':
        raise ValueError('Unsupported renderer')
    cancellation_point()
    state['outputs'] = verified_outputs(folder, request, state['outputs'])
    if len(state['outputs']) != state['total_frames']:
        raise RuntimeError('Final output verification failed or frames missing')
    state.update(state='completed', phase='finished', finished_at=time.time()); status()
except Cancelled:
    state.update(state='cancelled', phase='finished', finished_at=time.time()); status()
except BaseException:
    state['error'] = traceback.format_exc()
    if child is not None and child.poll() is None:
        # Ask the renderer to skip future frames and drain its current frame safely.
        atomic_json(folder / 'cancel.json', {'reason': 'worker_error', 'requested_at': time.time()})
        state['phase'] = 'stopping_after_error'; status()
        child.wait()
    state.update(state='failed', phase='finished', finished_at=time.time()); status()
    raise
