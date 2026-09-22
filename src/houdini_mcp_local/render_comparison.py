"""Read-only local convergence evidence; never confuses a proxy with ground truth."""
import io
import json
import math
import statistics
from . import render_jobs
from .render_preview import read_preview


def identity(request):
    keys = ('scene_sha256', 'rop_path', 'composite_node', 'source_cop_node', 'width', 'height',
            'asset_path', 'parameters', 'renderer', 'region', 'xpu_surface', 'adapter_version', 'diagnostics')
    result = {k: request.get(k) for k in keys}
    result['libraries'] = sorted(v['sha256'] for v in request.get('libraries', []))
    result['dependencies'] = sorted((v['path'], v['sha256']) for v in request.get('external_dependencies', []))
    # Sampling changes are permitted; stochastic locking/seed are held fixed.
    result['seed'] = {k: request.get('sampling', {}).get(k) for k in ('seed', 'sample_lock')}
    return result


def noise_proxy(pixels, width, height):
    gray = [.2126*p[0]+.7152*p[1]+.0722*p[2] for p in pixels]
    differences = [gray[y*width+x]-2*gray[y*width+x+1]+gray[y*width+x+2]
                   for y in range(height) for x in range(width-2)]
    differences += [gray[y*width+x]-2*gray[(y+1)*width+x]+gray[(y+2)*width+x]
                    for y in range(height-2) for x in range(width)]
    if not differences:
        return None
    middle = statistics.median(differences)
    return statistics.median(abs(v-middle) for v in differences) / (.67448975 * math.sqrt(6))


def compare(job_ids, frame=None):
    from PIL import Image
    if not isinstance(job_ids, list) or not 2 <= len(job_ids) <= 8 or len(set(job_ids)) != len(job_ids):
        raise ValueError('Provide 2-8 distinct job IDs in intended comparison order')
    baseline = None; previous = None; selected_frame = frame; rows = []
    for identifier in job_ids:
        request = json.loads((render_jobs.job_dir(identifier)/'request.json').read_text(encoding='utf-8'))
        signature = identity(request)
        if baseline is not None and signature != baseline:
            raise ValueError('Incompatible scene/camera/region/renderer/dependencies or stochastic seed')
        baseline = signature
        meta, raw = read_preview(identifier, selected_frame)
        selected_frame = meta['frame']
        state = render_jobs.get_status(identifier)
        entry = next(v for v in state['outputs'] if v['frame'] == selected_frame)
        if not render_jobs.verified_outputs(render_jobs.job_dir(identifier), request, [entry]):
            raise ValueError('Frame artifacts failed verification')
        with Image.open(io.BytesIO(raw)) as source:
            region = request.get('region') or [0, 0, source.width, source.height]
            image = source.convert('RGB').crop(tuple(region))
            pixels = list(image.getdata())
            row = dict(job_id=identifier, frame=selected_frame, sampling=request.get('sampling', {}),
                       effective_settings=entry.get('effective_settings'), region=region,
                       noise_proxy_display_255=noise_proxy(pixels, image.width, image.height),
                       timings=entry.get('timings'), png=meta['png'])
        if previous is not None:
            row['previous_mae_display_255'] = sum(abs(a-b) for p,q in zip(previous,pixels) for a,b in zip(p,q)) / (3*len(pixels))
        previous = pixels; rows.append(row)
    return {'comparisons': rows, 'compatible': True,
            'limitations': 'Display-space ROI second-difference MAD is a noise proxy contaminated by edges/material detail; MAE is change, not ground-truth error. No automatic convergence or denoise acceptance.'}
