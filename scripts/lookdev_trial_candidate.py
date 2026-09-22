"""Create isolated Mantra PBR camera/GI candidates from the accepted snapshot.

Run with hython. Geometry/materials remain frozen; this is not an MCP upgrade.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path
import hou

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from paired_frame_candidate import aim, detailed

SOURCE = ROOT / 'assets/upper-assembly-v01/candidate-02'
OUT = ROOT / 'assets/lookdev-trial-v01/candidate-01'
EVIDENCE = ROOT / 'evidence/lookdev-trial-v01'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parameters(node):
    return {p.name():p.rawValue() for p in node.parms()}


def alpha_safe_view(view, glob, pack, transform, split):
    """The nonlinear view operates on straight RGB; COP output stays premultiplied."""
    epsilon = view.createNode('constant', 'alpha_epsilon')
    epsilon.parm('floatdef').set(1e-6)
    denominator = view.createNode('max', 'safe_alpha')
    denominator.setInput(0, glob, glob.outputIndex('A'))
    denominator.setInput(1, epsilon)
    unpremultiply = view.createNode('divide', 'straight_linear_rgb')
    unpremultiply.setInput(0, pack); unpremultiply.setInput(1, denominator)
    transform.setInput(0, unpremultiply)
    premultiply = view.createNode('multiply', 'premultiplied_display_rgb')
    premultiply.setInput(0, transform); premultiply.setInput(1, glob, glob.outputIndex('A'))
    split.setInput(0, premultiply)


def install_view(net):
    source = net.node('source')
    source.parm('linearize').set(0)
    view = net.createNode('vopcop2filter', 'aces_sdr_preview')
    view.setInput(0, source)
    glob, output = view.node('global1'), view.node('output1')
    pack = view.createNode('floattovec', 'pack_linear_rec709')
    transform = view.createNode('ocio_transformview', 'aces_sdr')
    split = view.createNode('vectofloat', 'unpack_display_rgb')
    for i, channel in enumerate('RGB'):
        pack.setInput(i, glob, glob.outputIndex(channel))
    transform.parm('fromspace').set('Linear Rec.709 (sRGB)')
    transform.parm('todisplay').set('sRGB - Display')
    transform.parm('toview').set('ACES 1.0 - SDR Video')
    transform.setInput(0, pack)
    split.setInput(0, transform)
    alpha_safe_view(view, glob, pack, transform, split)
    for i, channel in enumerate('RGB'):
        output.setInput(output.inputIndex(channel), split, i)
    output.setInput(output.inputIndex('A'), glob, glob.outputIndex('A'))
    net.node('OUT').setInput(0, view)
    view.layoutChildren(); net.layoutChildren()


def main():
    plan = json.loads((ROOT / 'assets/lookdev-design-v01/lighting-camera-plan.json').read_text(encoding='utf-8-sig'))
    assert digest(SOURCE/'assembly.hip') == plan['source_sha256']
    OUT.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((SOURCE/'native-report.json').read_text())
    library = OUT/Path(manifest['library']).name
    shutil.copy2(manifest['library'], library)
    hou.hipFile.load(str(SOURCE/'assembly.hip'), suppress_save_prompt=True)
    hou.hda.installFile(str(library))
    for definition in hou.hda.definitionsInFile(str(library)):
        definition.setIsPreferred(True)
    hou.hda.uninstallFile(manifest['library'])
    asset = hou.node('/obj/two_tier_assembly/asset')
    parts = detailed(asset.geometry())
    assert parts == manifest['parts'], 'Source component fingerprint mismatch'
    material_state = {n.path():parameters(n) for n in hou.node('/mat').children()}
    lights = [n for n in hou.node('/obj').children() if n.parm('light_intensity')]
    assert len(lights) == 9  # Eight direct/environment lights plus legacy ambient.
    light_state = {n.path():parameters(n) for n in lights}
    install_view(hou.node('/img/accept_preview'))
    cameras = {}
    preview_sizes = {'C1':(960,540),'C2':(720,960),'C3':(960,640)}
    for spec in plan['cameras']:
        c = hou.node('/obj').createNode('cam', 'lookdev_'+spec['id'])
        c.parm('projection').set('perspective')
        c.parm('focal').set(spec['focal_mm']); c.parm('aperture').set(spec['aperture_mm'])
        c.parmTuple('res').set(preview_sizes[spec['id']])
        for p in ('enable_dof','allowmotionblur'):
            if c.parm(p): c.parm(p).set(0)
        aim(c, spec['target'], [a-b for a,b in zip(spec['position'],spec['target'])])
        cameras[spec['id']] = c.path()
    rop = hou.node('/out/accept_render')
    rop.parm('camera').set(cameras['C1'])
    rop.parm('vm_renderengine').set('pbrraytrace')
    rop.parm('vm_samplelock').set(1); rop.parm('vm_randomseed').set(0)
    if rop.parm('allowmotionblur'): rop.parm('allowmotionblur').set(0)
    hou.setFrame(1)
    report = dict(source=str(SOURCE/'assembly.hip'), source_sha256=plan['source_sha256'],
                  library=str(library), library_sha256=digest(library), cameras=cameras,
                  preview_sizes=preview_sizes, parts=parts, materials=material_state, lights=light_state,
                  color=dict(source='Linear Rec.709 (sRGB)', display='sRGB - Display', view='ACES 1.0 - SDR Video',
                             file_cop_linearize=0, exposure_stops=0, raw_exr='unchanged linear HDR'),
                  source_geometry_verified=True, candidates={})
    config = Path(hou.expandString('$OCIO'))
    if config.is_file():
        report['color']['ocio_config'] = dict(path=str(config), sha256=digest(config))
    for limit in (0,1,2):
        rop.parm('vm_diffuselimit').set(limit)
        hip = OUT/f'C1-GI{limit}-A.hip'
        hou.hipFile.save(str(hip))
        report['candidates'][hip.stem]=dict(path=str(hip),sha256=digest(hip),camera='C1',diffuse_limit=limit,light_pose='A')
    assert {n.path():parameters(n) for n in lights} == light_state
    assert {n.path():parameters(n) for n in hou.node('/mat').children()} == material_state
    assert digest(SOURCE/'assembly.hip') == plan['source_sha256']
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(created=list(report['candidates']), parts=len(parts), library=str(library))),flush=True)


if __name__ == '__main__': main()
