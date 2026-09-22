"""Opt-in render decomposition and separate OIDN outputs, Houdini 20.5.

Imports Houdini/USD only inside runtime functions, so request validation is
available in the MCP process.  No image or source scene is overwritten.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time


LPE = {
    'direct_diffuse': 'C<RD>[LO]',
    'indirect_diffuse': 'C<RD>.+[LO]',
    'direct_specular': 'C<RG>[LO]',
    'indirect_specular': 'C<RG>.+[LO]',
}


def validate_diagnostics(value=None):
    if value is None:
        return {'aovs': [], 'denoise': False}
    if not isinstance(value, dict) or set(value) - {'aovs', 'denoise'}:
        raise ValueError('diagnostics accepts only aovs and denoise')
    aovs = value.get('aovs', [])
    denoise = value.get('denoise', False)
    if not isinstance(aovs, list) or any(not isinstance(v, str) or v not in LPE for v in aovs):
        raise ValueError('diagnostics.aovs must be a list of supported AOV names')
    if len(aovs) != len(set(aovs)):
        raise ValueError('diagnostics.aovs must not contain duplicates')
    if type(denoise) is not bool:
        raise ValueError('diagnostics.denoise must be boolean')
    return {'aovs': list(aovs), 'denoise': denoise}


def configure_mantra(rop, diagnostics=None):
    """Append explicit LPE planes; never erase unrelated user extra planes."""
    diagnostics = validate_diagnostics(diagnostics)
    result = {}
    if not diagnostics['aovs']:
        return result
    count = rop.evalParm('vm_numaux')
    existing = {rop.evalParm('vm_channel_plane' + str(i)): i for i in range(1, count + 1)}
    for name in diagnostics['aovs']:
        channel = 'workai_' + name
        index = existing.get(channel)
        if index is not None and rop.evalParm('vm_variable_plane' + str(index)) != 'lpe:' + LPE[name]:
            raise ValueError('Existing AOV channel conflicts with diagnostics: ' + channel)
        if index is None:
            count += 1
            rop.parm('vm_numaux').set(count)
            index = count
        for key, value in {'vm_disable_plane': 0, 'vm_variable_plane': 'lpe:' + LPE[name],
                           'vm_channel_plane': channel, 'vm_vextype_plane': 'vector',
                           'vm_quantize_plane': 'float', 'vm_usefile_plane': 0,
                           'vm_componentexport': 0, 'vm_gamma_plane': 1.0,
                           'vm_gain_plane': 1.0}.items():
            rop.parm(key + str(index)).set(value)
        result[name] = {'channel': channel, 'lpe': LPE[name], 'index': index}
    return result


def configure_usd(usdpath, request):
    """Append RenderVars to each render product without replacing beauty."""
    diagnostics = validate_diagnostics(request.get('diagnostics'))
    if not diagnostics['aovs']:
        return {}
    from pxr import Usd, UsdRender, Sdf
    stage = Usd.Stage.Open(str(usdpath))
    if stage is None:
        raise ValueError('Unable to open USD diagnostics input')
    products = [UsdRender.Product(p) for p in stage.Traverse() if p.IsA(UsdRender.Product)]
    if not products:
        raise ValueError('USD diagnostics require a render product')
    result = {}
    for name in diagnostics['aovs']:
        path = '/Render/Vars/Workai_' + name
        existing = stage.GetPrimAtPath(path)
        if existing:
            previous = UsdRender.Var(existing)
            if (not existing.IsA(UsdRender.Var)
                    or previous.GetSourceNameAttr().Get() != LPE[name]
                    or previous.GetSourceTypeAttr().Get() != 'lpe'
                    or existing.GetAttribute('driver:parameters:aov:name').Get() != 'workai_' + name):
                raise ValueError('Existing USD RenderVar conflicts with diagnostics: ' + path)
        var = UsdRender.Var.Define(stage, path)
        var.CreateDataTypeAttr('color3f')
        var.CreateSourceNameAttr(LPE[name]); var.CreateSourceTypeAttr('lpe')
        channel = 'workai_' + name
        var.GetPrim().CreateAttribute('driver:parameters:aov:name', Sdf.ValueTypeNames.String).Set(channel)
        var.GetPrim().CreateAttribute('driver:parameters:aov:format', Sdf.ValueTypeNames.Token).Set('color3f')
        for product in products:
            targets = product.GetOrderedVarsRel().GetTargets()
            if var.GetPath() not in targets:
                product.CreateOrderedVarsRel().SetTargets(targets + [var.GetPath()])
        result[name] = {'channel': channel, 'lpe': LPE[name], 'render_var': path}
    stage.GetRootLayer().Save()
    return result


def _file_info(path):
    raw = path.read_bytes()
    if not raw:
        raise RuntimeError('Empty diagnostic output: ' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _load(source, path):
    source.parm('filename1').set(path.as_posix())
    source.parm('singleimage').set(1)
    source.parm('reload').pressButton()


def _pixels(source, plane='C'):
    import numpy as np
    from .image_inspection import inspect_pixels
    rgb = np.asarray(source.allPixels(plane), dtype=np.float32).reshape(-1, 3)
    alpha = source.allPixels('A') if plane == 'C' and 'A' in source.planes() else None
    check = inspect_pixels(rgb, alpha)
    if not check['finite']:
        raise RuntimeError('Nonfinite diagnostic pixels: ' + plane)
    return rgb, check


def _preview(source, comp, exr, png, frame, dimensions):
    _load(source, exr)
    if (source.xRes(), source.yRes()) != dimensions:
        raise RuntimeError('Unexpected diagnostic EXR dimensions')
    rgb, check = _pixels(source)
    _pixels(comp)  # Floating point output must also be finite.
    comp.saveImage(png.as_posix(), (frame, frame))
    header = png.read_bytes()[:24]
    if not header.startswith(b'\x89PNG\r\n\x1a\n') or struct.unpack('>II', header[16:24]) != dimensions:
        raise RuntimeError('Invalid diagnostic PNG or dimensions')
    return {'exr': _file_info(exr), 'png': _file_info(png), 'pixels': check,
            'width': dimensions[0], 'height': dimensions[1]}, rgb


def compare_pixels(before, after, width, height):
    """Difference/detail evidence; without clean truth this is not noise quality."""
    import numpy as np
    a = np.asarray(before, dtype=np.float32).reshape(height, width, 3)
    b = np.asarray(after, dtype=np.float32).reshape(height, width, 3)
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Nonfinite comparison pixels')
    luma = np.array([.2126, .7152, .0722], dtype=np.float32)
    def gradient(image):
        lum = image @ luma
        return float((np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean()) * .5)
    first, second = gradient(a), gradient(b)
    return {'mean_absolute_rgb_difference': float(np.abs(a - b).mean()),
            'maximum_absolute_rgb_difference': float(np.abs(a - b).max()),
            'raw_mean_luminance_gradient': first, 'denoised_mean_luminance_gradient': second,
            'gradient_retention_ratio': second / first if first > 1e-12 else None,
            'note': 'Gradient change mixes noise removal and genuine detail loss. It is not a quality score; inspect bevels, holes, threads and small pads at full resolution.'}


def postprocess(folder, frame, request, source, comp):
    """Write explicit AOV and denoised variants; restore original COP source.

    Return optional output metadata. All nested exr/png values have the same
    path/bytes/sha256 shape as beauty output, for resume integrity validation.
    """
    import hou
    import numpy as np
    diagnostics = validate_diagnostics(request.get('diagnostics'))
    if not diagnostics['aovs'] and not diagnostics['denoise']:
        return {}
    folder = Path(folder)
    raw = folder / f'raw_{frame:04}.exr'
    original_name = source.parm('filename1').unexpandedString()
    original_single = source.evalParm('singleimage')
    raw_info = _file_info(raw)
    raw_png = folder / f'frame_{frame:04}.png'
    original_png = _file_info(raw_png) if raw_png.exists() else None
    dims = (request['width'], request['height'])
    result = {'aovs': {}, 'evidence': {'raw_sha256_before': raw_info['sha256'],
               'houdini_version': hou.applicationVersionString(), 'color_pipeline': 'Existing preview COP chain, shared by raw and variants.'}}
    transient = []
    started = time.perf_counter()
    try:
        _load(source, raw)
        if (source.xRes(), source.yRes()) != dims:
            raise RuntimeError('Unexpected raw dimensions for diagnostics')
        original, _ = _pixels(source)
        planes = source.planes()
        arrays = {}
        for name in diagnostics['aovs']:
            channel = 'workai_' + name
            if channel not in planes:
                raise RuntimeError('Requested AOV missing from renderer output: ' + channel)
            _load(source, raw)
            arrays[name], check = _pixels(source, channel)
            # COP plane renaming is used instead of re-encoding pixels externally.
            strip = source.parent().createNode('delete')
            transient.append(strip); strip.setInput(0, source)
            strip.parm('scope').set('C')
            rename = source.parent().createNode('rename')
            transient.append(rename); rename.setInput(0, strip)
            rename.parm('from').set(channel); rename.parm('to').set('C')
            exr = folder / f'aov_{name}_{frame:04}.exr'
            png = folder / f'aov_{name}_{frame:04}.png'
            if exr.exists() or png.exists():
                raise FileExistsError('Diagnostic output already exists: ' + str(exr))
            rename.saveImage(exr.as_posix(), (frame, frame))
            item, extracted = _preview(source, comp, exr, png, frame, dims)
            if not np.allclose(extracted, arrays[name], rtol=1e-6, atol=1e-7):
                raise RuntimeError('Extracted AOV differs from raw channel: ' + channel)
            item.update(channel=channel, lpe=LPE[name], pixels=check)
            result['aovs'][name] = item
            transient.remove(rename); rename.destroy()
            transient.remove(strip); strip.destroy()
        if len(arrays) == len(LPE):
            summed = sum(arrays.values())
            result['evidence']['four_aov_sum_vs_beauty'] = {
                'mean_absolute_residual': float(np.abs(original - summed).mean()),
                'maximum_absolute_residual': float(np.abs(original - summed).max()),
                'note': 'Four reflective lobes are not universally the complete beauty. Emission visible to camera, transmission, subsurface and volume may remain. Residual is evidence, not a failure.'}
        if diagnostics['denoise']:
            exr = folder / f'denoised_{frame:04}.exr'
            png = folder / f'denoised_{frame:04}.png'
            if exr.exists() or png.exists():
                raise FileExistsError('Denoised output already exists: ' + str(exr))
            executable = Path(hou.expandString('$HFS')) / 'bin' / ('idenoise.exe' if os.name == 'nt' else 'idenoise')
            if not executable.is_file():
                raise RuntimeError('Houdini idenoise executable is unavailable')
            command = [str(executable), str(raw), str(exr), '-d', 'oidn', '--aovs', 'C', '-V', '1']
            proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors='replace', timeout=300,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            log = folder / f'denoise_{frame:04}.log'
            log.write_text(json.dumps({'command': command, 'exit_code': proc.returncode,
                                       'stdout_stderr': proc.stdout}, indent=2), encoding='utf-8')
            if proc.returncode:
                raise RuntimeError('OIDN failed; see ' + str(log))
            item, denoised = _preview(source, comp, exr, png, frame, dims)
            item.update(denoiser='oidn', auxiliary_inputs=[], command=command, log=_file_info(log),
                        comparison=compare_pixels(original, denoised, *dims),
                        limitation='Beauty-only spatial OIDN. No albedo/normal guidance or temporal consistency claim.')
            result['denoised'] = item
        after = _file_info(raw)
        if raw_info != after:
            raise RuntimeError('Original EXR changed during diagnostic processing')
        if original_png is not None and original_png != _file_info(raw_png):
            raise RuntimeError('Original PNG changed during diagnostic processing')
        result['evidence']['raw_sha256_after'] = after['sha256']
        result['evidence']['original_png_preserved'] = original_png is not None
        result['evidence']['seconds'] = time.perf_counter() - started
        return result
    finally:
        for node in reversed(transient):
            node.destroy()
        source.parm('filename1').set(original_name)
        source.parm('singleimage').set(original_single)
        source.parm('reload').pressButton()
