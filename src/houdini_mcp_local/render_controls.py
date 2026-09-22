"""Native renderer controls. All mutations are confined to worker snapshots."""
from .render_options import region_ndc

PARMS = {'min_rays': 'vm_minraysamples', 'max_rays': 'vm_maxraysamples',
         'noise_threshold': 'vm_variance', 'sample_lock': 'vm_samplelock', 'seed': 'vm_randomseed'}


def inspect_mantra(rop):
    return dict(pixel_samples=[rop.evalParm('vm_samplesx'), rop.evalParm('vm_samplesy')],
                adaptive=rop.evalParm('vm_dorayvariance'),
                **{key: rop.evalParm(parm) for key, parm in PARMS.items()})


def configure_mantra(rop, request):
    before = inspect_mantra(rop)
    values = request.get('sampling', {})
    axis = int(request.get('pixel_samples', 4) ** .5)
    x, y = values.get('pixel_samples', [axis, axis])
    rop.parm('vm_samplesx').set(x); rop.parm('vm_samplesy').set(y)
    for key, parm in PARMS.items():
        if key in values:
            rop.parm(parm).set(values[key])
    if any(k in values for k in ('min_rays', 'max_rays', 'noise_threshold')):
        rop.parm('vm_dorayvariance').set(1)
    return {'before': before, 'effective': inspect_mantra(rop),
            'source': 'worker ROP parameter readback after overrides'}


def configure_mantra_region(camera, request):
    if request.get('region') is None:
        return {'region': None, 'camera_crop': [camera.evalParm(p) for p in ('cropl', 'cropb', 'cropr', 'cropt')]}
    ndc = region_ndc(request)
    for parm, value in zip(('cropl', 'cropb', 'cropr', 'cropt'), ndc):
        camera.parm(parm).set(value)
    return {'region': request['region'], 'camera_crop': [camera.evalParm(p) for p in ('cropl', 'cropb', 'cropr', 'cropt')],
            'source': 'native camera crop; unchanged full-frame projection and resolution'}


def configure_usd_region(usdpath, request):
    if request.get('region') is None:
        return {'region': None}
    from pxr import Usd, UsdRender, Gf
    stage = Usd.Stage.Open(str(usdpath))
    settings = UsdRender.Settings.Get(stage, '/Render/Settings')
    ndc = region_ndc(request)
    settings.CreateDataWindowNDCAttr(Gf.Vec4f(*ndc))
    stage.GetRootLayer().Save()
    return {'region': request['region'], 'dataWindowNDC': list(settings.GetDataWindowNDCAttr().Get()),
            'source': 'USD render settings dataWindowNDC'}
