"""Portable render option and evidence helpers (no Houdini import)."""
import re
import json
import math


def options(renderer='mantra', quality='preview', sampling=None):
    if renderer not in ('mantra', 'karma_xpu'):
        raise ValueError('renderer must be mantra or karma_xpu')
    if quality not in ('preview', 'final'):
        raise ValueError('quality must be preview or final')
    samples = (16 if quality == 'preview' else 64) if renderer == 'karma_xpu' else (4 if quality == 'preview' else 16)
    sampling = {} if sampling is None else sampling
    if not isinstance(sampling, dict):
        raise ValueError('sampling must be an object')
    allowed = {'pixel_samples'} if renderer == 'karma_xpu' else {'pixel_samples', 'min_rays', 'max_rays', 'noise_threshold', 'sample_lock', 'seed'}
    if set(sampling) - allowed:
        raise ValueError('Unsupported sampling fields: ' + ', '.join(sorted(set(sampling) - allowed)))
    result = dict(sampling)
    if 'pixel_samples' in sampling:
        value = sampling['pixel_samples']
        if renderer == 'mantra':
            if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(v) is not int or not 1 <= v <= 32 for v in value):
                raise ValueError('Mantra pixel_samples must be [x,y], each integer 1..32')
            result['pixel_samples'] = list(value)
            samples = value[0] * value[1]
        else:
            if type(value) is not int or not 1 <= value <= 4096:
                raise ValueError('XPU pixel_samples must be an integer 1..4096')
            samples = value
    for key in ('min_rays', 'max_rays'):
        if key in sampling and (type(sampling[key]) is not int or not 1 <= sampling[key] <= 4096):
            raise ValueError(key + ' must be an integer 1..4096')
    if 'min_rays' in sampling or 'max_rays' in sampling:
        if not {'min_rays', 'max_rays'} <= sampling.keys() or sampling['min_rays'] > sampling['max_rays']:
            raise ValueError('Supply both min_rays and max_rays with min <= max')
    if 'noise_threshold' in sampling:
        value = sampling['noise_threshold']
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError('noise_threshold must be finite and in (0,1]')
    if 'sample_lock' in sampling and type(sampling['sample_lock']) is not bool:
        raise ValueError('sample_lock must be boolean')
    if 'seed' in sampling and (type(sampling['seed']) is not int or not 0 <= sampling['seed'] <= 2147483647):
        raise ValueError('seed must be an integer 0..2147483647')
    return {'renderer': renderer, 'quality': quality, 'pixel_samples': samples, 'sampling': result}


def validate_region(region, width, height):
    if region is None:
        return None
    if not isinstance(region, (list, tuple)) or len(region) != 4 or any(type(v) is not int for v in region):
        raise ValueError('region must be [left,top,right,bottom] in full-frame pixels, exclusive upper bounds')
    left, top, right, bottom = region
    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
        raise ValueError('region is empty or outside the full-frame resolution')
    return list(region)


def region_ndc(request):
    region = request.get('region') or [0, 0, request['width'], request['height']]
    l, t, r, b = region
    return [l / request['width'], 1 - b / request['height'], r / request['width'], 1 - t / request['height']]


def extensions(renderer, width, height, region=None, xpu_surface=None, diagnostics=None):
    from .render_diagnostics import validate_diagnostics
    if xpu_surface is not None:
        if renderer != 'karma_xpu' or not isinstance(xpu_surface, dict):
            raise ValueError('xpu_surface requires karma_xpu and an object')
        allowed = {'light_paths', 'excluded_object_paths', 'excluded_light_paths'}
        if set(xpu_surface) - allowed:
            raise ValueError('Unknown xpu_surface fields')
        for key, value in xpu_surface.items():
            if not isinstance(value, list) or len(value) > 128 or any(not isinstance(p, str) or not p.startswith('/obj/') for p in value) or len(set(value)) != len(value):
                raise ValueError('xpu_surface paths must be unique absolute /obj paths, maximum 128')
    return dict(region=validate_region(region, width, height), xpu_surface=xpu_surface,
                diagnostics=validate_diagnostics(diagnostics))


def device_evidence(log, frame):
    """Only attribute device contribution from this frame's completed log block."""
    blocks = list(re.finditer(r'>>> Render[^\n]*frame:\s*(-?\d+)', log))
    selected = ''
    for index, match in enumerate(blocks):
        if int(match.group(1)) == frame:
            selected = log[match.end():blocks[index + 1].start() if index + 1 < len(blocks) else len(log)]
    devices = []
    for block in re.split(r'\nDevice \d+\s*\n', selected)[1:]:
        kind = re.search(r'^Type\s*:\s*(.+)$', block, re.M)
        name = re.search(r'^Name\s*:\s*(.+)$', block, re.M)
        contribution = re.search(r'^Contrib\s*:\s*([\d.]+)%', block, re.M)
        if kind and name and contribution:
            devices.append(dict(type=kind.group(1).strip(), name=name.group(1).strip(), contribution_percent=float(contribution.group(1))))
    return {'verified': any(d['type'].lower() == 'optix' and d['contribution_percent'] > 0 for d in devices),
            'devices': devices, 'source': 'husk completed-frame render statistics', 'frame': frame}


def cancellation_receipt(folder, pending):
    """Prove a known pre-frame cancellation, without masking a failed current frame."""
    stopped = folder / 'renderer-stop.json'
    if not stopped.exists() or not (folder / 'cancel.json').exists():
        return None
    stop = json.loads(stopped.read_text())
    if (stop.get('reason') != 'cancel_requested' or stop.get('frame') not in pending
            or (folder / f"start_{stop['frame']:04}.json").exists()
            or not all((folder / p.name.replace('start_', 'ready_')).exists() for p in folder.glob('start_*.json'))):
        return None
    return stop
