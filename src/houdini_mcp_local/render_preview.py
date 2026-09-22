"""Bounded, read-only access to recorded render images."""
import hashlib
import struct
from pathlib import Path
from . import render_jobs


def read_preview(job_id, frame=None, variant='raw'):
    state = render_jobs.get_status(job_id)
    outputs = state.get('outputs', [])
    if frame is not None and type(frame) is not int:
        raise ValueError('frame must be an integer')
    selected = [v for v in outputs if frame is None or v['frame'] == frame]
    if not selected:
        raise ValueError('No recorded completed frame available')
    item = max(selected, key=lambda v: v['frame'])
    visual = item.get('visual_check')
    if variant == 'raw':
        record = item['png']
    elif variant == 'denoised':
        record = item.get('diagnostics', {}).get('denoised', {}).get('png')
        visual = {'raw': item.get('diagnostics', {}).get('denoised', {}).get('pixels'), 'source': 'denoised linear EXR'}
    elif variant in ('direct_diffuse', 'indirect_diffuse', 'direct_specular', 'indirect_specular'):
        record = item.get('diagnostics', {}).get('aovs', {}).get(variant, {}).get('png')
        visual = {'raw': item.get('diagnostics', {}).get('aovs', {}).get(variant, {}).get('pixels'), 'source': 'AOV linear EXR'}
    else:
        raise ValueError('Unknown preview variant')
    if not record:
        raise ValueError('Requested variant was not recorded for this frame')
    path = Path(record['path']).resolve()
    if path.parent != render_jobs.job_dir(job_id).resolve():
        raise ValueError('Preview path is outside its job')
    if not 0 < path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('Preview exceeds size limit or is empty')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise ValueError('Preview fingerprint changed; resume to repair the frame')
    if len(raw) < 33 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[8:16] != b'\x00\x00\x00\rIHDR':
        raise ValueError('Invalid PNG header')
    width, height = struct.unpack('>II', raw[16:24])
    if not (128 <= width <= 1920 and 128 <= height <= 1080):
        raise ValueError('Preview dimensions exceed supported range')
    metadata = dict(job_id=job_id, state=state['state'], frame=item['frame'],
                    renderer=state.get('renderer', 'mantra'), quality=state.get('quality', 'scene'),
                    width=width, height=height, png=record, variant=variant,
                    visual_check=visual, timings=item.get('timings'),
                    gpu_evidence=item.get('gpu_evidence'), reused_from_job=item.get('reused_from_job'))
    return metadata, raw
