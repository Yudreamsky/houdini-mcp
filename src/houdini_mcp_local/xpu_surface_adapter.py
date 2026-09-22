"""Explicit single-asset, single-frame polygon/Principled -> MaterialX adapter.

This is a bounded *physical* material translation, not a BSDF-equivalence claim.
Numbers remain scene-linear Rec.709; callers must use husk --ocio 0 and the
matching Rec.709 display pipeline. No material or light is silently replaced.
"""
import hashlib
import json
import math
from pathlib import Path

import hou

ADAPTER_VERSION = 1
SURFACE_KEYS = frozenset(('light_paths', 'excluded_object_paths', 'excluded_light_paths'))


def _value(node, name, default=None):
    parm = node.parm(name)
    return parm.eval() if parm is not None else default


def _finite(values, label):
    if any(not math.isfinite(float(v)) for v in values):
        raise ValueError('Nonfinite ' + label)


def _paths(options, key):
    values = options.get(key, [])
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.startswith('/obj/') for v in values):
        raise ValueError('xpu_surface.' + key + ' must be a list of absolute /obj paths')
    if len(values) != len(set(values)):
        raise ValueError('Duplicate xpu_surface.' + key)
    return set(values)


def _scope(request, asset):
    options = request.get('xpu_surface')
    if not isinstance(options, dict) or set(options) - SURFACE_KEYS:
        raise ValueError('xpu_surface requires an object containing only ' + ', '.join(sorted(SURFACE_KEYS)))
    selected = _paths(options, 'light_paths')
    excluded_lights = _paths(options, 'excluded_light_paths')
    excluded_objects = _paths(options, 'excluded_object_paths')
    if not selected or selected & excluded_lights:
        raise ValueError('Select at least one light; selected and excluded lights must be disjoint')
    owner = asset.parent()
    while owner is not None and not isinstance(owner, hou.ObjNode):
        owner = owner.parent()
    if owner is None or owner.type().name() != 'geo':
        raise ValueError('Selected SOP must belong to a geometry OBJ')
    if owner.path() in excluded_objects:
        raise ValueError('Cannot exclude selected asset owner')
    all_lights, objects = {}, {}
    for node in hou.node('/obj').allSubChildren():
        if not isinstance(node, hou.ObjNode):
            continue
        if node.parm('light_enable') is not None:
            if _value(node, 'light_enable', 1):
                all_lights[node.path()] = node
        elif node.type().name() in ('geo', 'instance') and node.isDisplayFlagSet():
            objects[node.path()] = node
        elif node.type().name() not in ('cam', 'null', 'subnet') and node.isDisplayFlagSet():
            raise ValueError('Unclassified displayed OBJ; explicitly unsupported: ' + node.path())
    missing = set(all_lights) - selected - excluded_lights
    if missing:
        raise ValueError('Unaccounted enabled lights; select or explicitly exclude: ' + ', '.join(sorted(missing)))
    if selected - set(all_lights) or excluded_lights - set(all_lights):
        raise ValueError('Selected/excluded light paths must identify enabled lights in this scene')
    other = set(objects) - {owner.path()}
    if other != excluded_objects:
        raise ValueError('Other displayed geometry must be explicitly and exactly excluded: ' + ', '.join(sorted(other)))
    for key, default in [('lightmask', '*'), ('shadowmask', '*'), ('vm_phantom', 0)]:
        if _value(owner, key, default) != default:
            raise ValueError('Unsupported object visibility/light linking: ' + owner.path() + '.' + key)
    return owner, [all_lights[p] for p in sorted(selected)], {
        'selected_object': owner.path(), 'selected_sop': asset.path(),
        'selected_lights': sorted(selected), 'excluded_objects': sorted(excluded_objects),
        'excluded_lights': sorted(excluded_lights),
        'selection_policy': 'Only the explicitly selected SOP is exported; sibling SOPs are not separate objects.',
    }


def _material(node):
    if node is None or node.type().name() != 'principledshader::2.0':
        raise ValueError('Expected unconnected principledshader::2.0 material, got ' + (node.path() if node else 'missing material'))
    if any(node.inputs()):
        raise ValueError('Connected Principled inputs are unsupported: ' + node.path())
    if hasattr(node, 'matchesCurrentDefinition') and not node.matchesCurrentDefinition():
        raise ValueError('Unlocked/edited Principled internals are unsupported: ' + node.path())
    for parm in node.parms():
        if ('_useTexture' in parm.name() or parm.name() in (
                'baseBumpAndNormal_enable', 'dispInput_enable', 'dispTex_enable', 'dispNoise_enable',
                'separateCoatNormals', 'basecolor_usePackedColor', 'opacpackedalpha')) and parm.eval():
            raise ValueError('Unsupported material feature: ' + node.path() + '.' + parm.name())
    for key in ('transparency', 'sss', 'sheen', 'coat', 'aniso', 'reflecttint', 'emitint', 'dispersion'):
        if abs(float(_value(node, key, 0))) > 1e-8:
            raise ValueError('Unsupported material lobe: ' + node.path() + '.' + key)
    if _value(node, 'specmodel') != 'ggx' or _value(node, 'opac', 1) != 1:
        raise ValueError('Only opaque GGX Principled materials are supported: ' + node.path())
    if tuple(node.parmTuple('opaccolor').eval()) != (1., 1., 1.):
        raise ValueError('Nonopaque material: ' + node.path())
    result = {'source_path': node.path(), 'shader_id': 'ND_standard_surface_surfaceshader',
              'base_color': list(node.parmTuple('basecolor').eval()),
              'use_Cd': bool(_value(node, 'basecolor_usePointColor', 0)),
              'metalness': float(_value(node, 'metallic')), 'specular': float(_value(node, 'reflect')),
              'specular_roughness': float(_value(node, 'rough')), 'specular_IOR': float(_value(node, 'ior'))}
    _finite(result['base_color'] + [result[k] for k in ('metalness', 'specular', 'specular_roughness', 'specular_IOR')], 'material values')
    for key in ('metalness', 'specular', 'specular_roughness'):
        if not 0 <= result[key] <= 1:
            raise ValueError('Material parameter outside supported [0,1]: ' + key)
    if any(v < 0 for v in result['base_color']) or result['specular_IOR'] <= 1:
        raise ValueError('Unsupported material color or IOR: ' + node.path())
    return result


def _light(node):
    if node.type().name() != 'hlight::2.0' or _value(node, 'light_type') not in (0, 2):
        raise ValueError('Only point and rectangular area hlight::2.0 are supported: ' + node.path())
    for name in ('coneenable', 'activeradiusenable', 'attenrampenable'):
        if _value(node, name, 0):
            raise ValueError('Unsupported light feature: ' + node.path() + '.' + name)
    for name in ('areamap', 'light_texture', 'areageometry'):
        if _value(node, name, ''):
            raise ValueError('Textured/geometry lights unsupported: ' + node.path() + '.' + name)
    if _value(node, 'atten_type', 2) != 2 or _value(node, 'shadowmask', '*') != '*':
        raise ValueError('Light requires physical attenuation and unrestricted shadow mask: ' + node.path())
    if _value(node, 'shadow_type', 1) != 1 or _value(node, 'shadow_intensity', 1) != 1:
        raise ValueError('Light requires full raytraced shadows: ' + node.path())
    if tuple(node.parmTuple('shadow_color').eval()) != (0., 0., 0.):
        raise ValueError('Colored shadows unsupported: ' + node.path())
    result = {'source_path': node.path(), 'type': 'rect' if _value(node, 'light_type') == 2 else 'point',
              'color': list(node.parmTuple('light_color').eval()),
              'intensity': float(_value(node, 'light_intensity')), 'exposure': float(_value(node, 'light_exposure', 0)),
              'normalize': bool(_value(node, 'normalizearea', 1)),
              'width': float(_value(node, 'areasize1', 1)), 'height': float(_value(node, 'areasize2', 1)),
              'transform': list(node.worldTransform().asTuple()),
              'source_attenuation_distance': float(_value(node, 'atten_dist', 1)),
              'source_primary_visibility': bool(_value(node, 'light_contribprimary', 0))}
    _finite(result['color'] + result['transform'] + [result[k] for k in ('intensity', 'exposure', 'width', 'height')], 'light values')
    if result['intensity'] < 0 or min(result['color']) < 0 or result['width'] <= 0 or result['height'] <= 0:
        raise ValueError('Invalid light intensity/color/size: ' + node.path())
    scale = node.worldTransform().extractScales()
    if any(abs(v - 1.) > 1e-5 for v in scale):
        raise ValueError('Scaled lights unsupported; set dimensions explicitly: ' + node.path())
    return result


def _attribute(geometry, name):
    """Return face-varying data using Houdini precedence (vertex, point, prim, detail)."""
    prims = geometry.prims()
    if geometry.findVertexAttrib(name):
        values, interpolation = [v.attribValue(name) for p in prims for v in p.vertices()], 'faceVarying'
    elif geometry.findPointAttrib(name):
        values, interpolation = [p.attribValue(name) for p in geometry.points()], 'vertex'
    elif geometry.findPrimAttrib(name):
        values, interpolation = [p.attribValue(name) for p in prims], 'uniform'
    elif geometry.findGlobalAttrib(name):
        values, interpolation = [geometry.attribValue(name)], 'constant'
    else:
        return None
    for value in values:
        if not isinstance(value, tuple) or len(value) != 3:
            raise ValueError(name + ' must be a three-component vector/color')
        _finite(value, name)
    return values, interpolation


def _orientation_audit(points, counts, indices, normals):
    """Numerically compare native N against left-handed Newell face normals.

    Houdini polygons are clockwise about their outward normal. Copying the
    indices to USD without leftHanded flips geometric sidedness even when N
    values themselves are bit-identical. Check all nondegenerate faces, not
    only a metadata token or a few representative vertices.
    """
    import numpy as np
    counts = np.asarray(counts, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    starts = np.r_[0, counts.cumsum()[:-1]]
    corners = np.asarray(points, dtype=np.float64)[indices]
    following = np.arange(len(indices)) + 1
    following[starts + counts - 1] = starts
    geometric = -np.add.reduceat(np.cross(corners, corners[following]), starts)
    geometric_length = np.linalg.norm(geometric, axis=1)
    report = {'usd_orientation': 'leftHanded', 'source_winding': 'Houdini clockwise/outward',
              'method': 'All-face left-handed Newell geometric normals versus averaged authored N',
              'faces': int(len(counts)), 'degenerate_faces': int((geometric_length <= 1e-12).sum())}
    if normals is None:
        report['authored_normals'] = 'absent; renderer generates using leftHanded winding'
        return report
    values, interpolation = normals
    authored = np.asarray(values, dtype=np.float64)
    zero_vectors = int((np.linalg.norm(authored, axis=1) <= 1e-12).sum())
    if interpolation == 'faceVarying':
        authored = np.add.reduceat(authored, starts)
    elif interpolation == 'vertex':
        authored = np.add.reduceat(authored[indices], starts)
    elif interpolation == 'constant':
        authored = np.repeat(authored, len(counts), axis=0)
    authored_length = np.linalg.norm(authored, axis=1)
    valid = (geometric_length > 1e-12) & (authored_length > 1e-12)
    dots = np.sum(geometric[valid] * authored[valid], axis=1) / (geometric_length[valid] * authored_length[valid])
    reversed_count = int((dots < -0.01).sum())
    report.update(compared_faces=int(valid.sum()), zero_authored_vectors=zero_vectors,
                  cancelled_average_face_normals=int((authored_length <= 1e-12).sum()),
                  opposed_faces=reversed_count, minimum_dot=float(dots.min()) if len(dots) else None,
                  median_dot=float(np.median(dots)) if len(dots) else None)
    # Nonzero smooth corner normals can cancel when averaged across a face.
    # Report those numerically indeterminate faces; they are not zero N values.
    if reversed_count or zero_vectors:
        raise ValueError('Authored N conflicts with Houdini left-handed polygon winding or contains zero N vectors: ' + json.dumps(report))
    return report


def _collect(request, camera):
    asset = hou.node(request.get('asset_path', ''))
    if asset is None or not isinstance(asset, hou.SopNode):
        raise ValueError('xpu_surface requires an explicit geometry SOP asset_path')
    if request.get('start_frame', 1) != request.get('end_frame', request.get('start_frame', 1)):
        raise ValueError('Physical surface adapter currently supports a single frame only')
    if camera is None or camera.type().name() != 'cam' or _value(camera, 'projection') not in (0, 1):
        raise ValueError('Surface adapter requires perspective or orthographic OBJ camera')
    if abs(float(_value(camera, 'aspect', 1)) - 1) > 1e-8:
        raise ValueError('Surface adapter requires square-pixel camera')
    for key in ('winx', 'winy'):
        if abs(float(_value(camera, key, 0))) > 1e-8:
            raise ValueError('Camera screen-window offsets unsupported: ' + key)
    if _value(camera, 'winsizex', 1) != 1 or _value(camera, 'winsizey', 1) != 1:
        raise ValueError('Camera screen-window scaling unsupported')
    if request.get('region') is None and any(abs(float(_value(camera, p, d)) - d) > 1e-8
            for p, d in (('cropl', 0), ('cropb', 0), ('cropr', 1), ('cropt', 1))):
        raise ValueError('Camera has a non-full crop; specify request.region explicitly rather than silently ignoring camera crop')
    camera_values = [float(_value(camera, p)) for p in ('aperture', 'focal', 'orthowidth', 'near', 'far')]
    _finite(camera_values, 'camera optical parameters')
    if any(v <= 0 for v in camera_values) or camera_values[-1] <= camera_values[-2]:
        raise ValueError('Camera aperture/focal/width/clipping must be positive with far > near')
    if _value(camera, 'focalunits', 'mm') != 'mm':
        raise ValueError('Camera focal units must be millimeters')
    if any(abs(v - 1.) > 1e-5 for v in camera.worldTransform().extractScales()):
        raise ValueError('Scaled camera unsupported')
    owner, light_nodes, scope = _scope(request, asset)
    geometry = asset.geometry()
    if geometry is None or asset.errors() or not geometry.prims():
        raise ValueError('Selected asset must cook nonempty without errors')
    if any(p.type() != hou.primType.Polygon or len(p.vertices()) < 3 or not p.isClosed() for p in geometry.prims()):
        raise ValueError('Only closed polygon faces are supported; unpack/convert curves, volumes and packed primitives explicitly')
    for name in ('material_override', 'shop_materialoverride', 'material_stylesheet'):
        if any((geometry.findGlobalAttrib(name), geometry.findPrimAttrib(name), geometry.findPointAttrib(name))):
            raise ValueError('Geometry material overrides unsupported: ' + name)
    for find, elems in ((geometry.findPrimAttrib, geometry.prims), (geometry.findPointAttrib, geometry.points),
                        (geometry.findVertexAttrib, lambda: (v for p in geometry.prims() for v in p.vertices()))):
        if find('Alpha') and any(not math.isfinite(float(p.attribValue('Alpha'))) or abs(float(p.attribValue('Alpha')) - 1) > 1e-8 for p in elems()):
            raise ValueError('Nonopaque geometry Alpha unsupported')
    if geometry.findGlobalAttrib('Alpha') and (not math.isfinite(float(geometry.attribValue('Alpha'))) or abs(float(geometry.attribValue('Alpha')) - 1) > 1e-8):
        raise ValueError('Nonopaque geometry Alpha unsupported')
    fallback = _value(owner, 'shop_materialpath', '')
    bindings = []
    has_binding = geometry.findPrimAttrib('shop_materialpath') is not None
    for prim in geometry.prims():
        path = prim.attribValue('shop_materialpath') if has_binding else ''
        path = path or fallback
        if not isinstance(path, str):
            raise ValueError('Material binding must be a node path string on primitive ' + str(prim.number()))
        material = asset.node(path) if path else None
        if material is None:
            raise ValueError('No effective material on primitive ' + str(prim.number()))
        bindings.append(material.path())
    materials = {p: _material(hou.node(p)) for p in sorted(set(bindings))}
    cd, normals = _attribute(geometry, 'Cd'), _attribute(geometry, 'N')
    if any(m['use_Cd'] for m in materials.values()) and cd is None:
        raise ValueError('Material reads Cd but selected geometry has no Cd')
    for point in geometry.points():
        _finite(point.position(), 'point position')
    winding = _orientation_audit([tuple(p.position()) for p in geometry.points()],
        [len(p.vertices()) for p in geometry.prims()],
        [v.point().number() for p in geometry.prims() for v in p.vertices()], normals)
    _finite(owner.worldTransform().asTuple(), 'object transform')
    _finite(camera.worldTransform().asTuple(), 'camera transform')
    return asset, owner, geometry, bindings, cd, normals, {
        'adapter': 'physical_surface', 'adapter_version': ADAPTER_VERSION,
        'scope': scope, 'materials': list(materials.values()),
        'lights': [_light(node) for node in light_nodes],
        'point_count': len(geometry.points()), 'polygon_count': len(geometry.prims()),
        'piece_count': len(set(geometry.primStringAttribValues('name'))) if geometry.findPrimAttrib('name') else None,
        'source_working_space': 'Linear Rec.709', 'usd_numeric_color_space': 'Linear Rec.709',
        'required_husk_options': ['--ocio', '0'], 'color_conversion': 'none; no ACEScg reinterpretation',
        'depth_of_field': 'disabled (no fStop authored)', 'motion_blur': 'disabled; static single frame',
        'path_depth': 'Karma defaults; Mantra GI/path-depth ROP controls are not migrated',
        'winding_validation': winding,
        'normal_interpolation': normals[1] if normals else 'generated by renderer',
        'Cd_interpolation': cd[1] if cd else None,
        'limitations': ['Single-frame polygon asset only; no textures, displacement, transmission, subsurface, sheen or coat.',
                       'Principled to MaterialX standard_surface is an approximate physical BSDF mapping, not pixel equivalence.',
                       'Houdini light intensity/exposure are copied numerically to USD; cross-renderer photometric equivalence is not claimed.',
                       'Only selected asset and lights are exported; all other enabled lights/displayed geometry must be explicitly excluded.'],
    }


def validate_surface(request, camera):
    """Read-only preflight; returns a JSON-serializable report or actionable error."""
    return _collect(request, camera)[-1]


def export_surface(folder, request, frames, cancellation_point):
    from pxr import Usd, UsdGeom, UsdShade, UsdLux, UsdRender, Sdf, Gf, Vt
    frames = list(frames)
    if len(frames) != 1:
        raise ValueError('Physical surface adapter currently supports a single frame only')
    cancellation_point()
    original_frame = hou.frame()
    try:
        hou.setFrame(frames[0])
        rop = hou.node(request['rop_path'])
        if rop is None or rop.parm('camera') is None:
            raise ValueError('Expected ROP with camera parameter')
        camera_node = rop.node(rop.evalParm('camera'))
        asset, owner, geometry, bindings, cd, normals, report = _collect(request, camera_node)
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'render.usdc'
        stage = Usd.Stage.CreateNew(str(path))
        stage.SetStartTimeCode(frames[0]); stage.SetEndTimeCode(frames[0])
        stage.SetFramesPerSecond(hou.fps()); stage.SetTimeCodesPerSecond(hou.fps())
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y); UsdGeom.SetStageMetersPerUnit(stage, 1.)
        world = UsdGeom.Xform.Define(stage, '/World'); stage.SetDefaultPrim(world.GetPrim())
        mesh = UsdGeom.Mesh.Define(stage, '/World/Asset')
        mesh.CreateSubdivisionSchemeAttr('none'); mesh.CreateDoubleSidedAttr(True)
        mesh.CreateOrientationAttr(UsdGeom.Tokens.leftHanded)
        mesh.AddTransformOp().Set(Gf.Matrix4d(*owner.worldTransform().asTuple()))
        mesh.CreatePointsAttr(Vt.Vec3fArray([tuple(p.position()) for p in geometry.points()]))
        mesh.CreateFaceVertexCountsAttr([len(p.vertices()) for p in geometry.prims()])
        mesh.CreateFaceVertexIndicesAttr([v.point().number() for p in geometry.prims() for v in p.vertices()])
        bbox = geometry.boundingBox()
        mesh.CreateExtentAttr([Gf.Vec3f(*bbox.minvec()), Gf.Vec3f(*bbox.maxvec())])
        if normals:
            mesh.CreateNormalsAttr(Vt.Vec3fArray(normals[0])); mesh.SetNormalsInterpolation(normals[1])
        primvars = UsdGeom.PrimvarsAPI(mesh)
        if cd:
            primvars.CreatePrimvar('Cd', Sdf.ValueTypeNames.Color3fArray, cd[1]).Set(Vt.Vec3fArray(cd[0]))
        for name in ('name', 'part_type'):
            if geometry.findPrimAttrib(name):
                values = list(geometry.primStringAttribValues(name))
                unique = sorted(set(values)); lookup = {v: i for i, v in enumerate(unique)}
                pv = primvars.CreatePrimvar(name, Sdf.ValueTypeNames.StringArray, 'uniform')
                pv.Set(unique); pv.SetIndices([lookup[v] for v in values])
        for index, params in enumerate(report['materials']):
            cancellation_point()
            material_path = '/World/Looks/Material_' + str(index)
            material = UsdShade.Material.Define(stage, material_path)
            material.GetPrim().SetCustomDataByKey('houdini_source', params['source_path'])
            shader = UsdShade.Shader.Define(stage, material_path + '/Surface')
            shader.CreateIdAttr('ND_standard_surface_surfaceshader')
            for key, value in [('base', 1.), ('metalness', params['metalness']), ('specular', params['specular']),
                               ('specular_roughness', params['specular_roughness']), ('specular_IOR', params['specular_IOR']),
                               ('transmission', 0.), ('subsurface', 0.), ('coat', 0.), ('emission', 0.)]:
                shader.CreateInput(key, Sdf.ValueTypeNames.Float).Set(value)
            color = shader.CreateInput('base_color', Sdf.ValueTypeNames.Color3f)
            if params['use_Cd']:
                reader = UsdShade.Shader.Define(stage, material_path + '/Cd')
                reader.CreateIdAttr('ND_geompropvalue_color3')
                reader.CreateInput('geomprop', Sdf.ValueTypeNames.String).Set('Cd')
                reader.CreateOutput('out', Sdf.ValueTypeNames.Color3f)
                multiply = UsdShade.Shader.Define(stage, material_path + '/Tint')
                multiply.CreateIdAttr('ND_multiply_color3')
                multiply.CreateInput('in1', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*params['base_color']))
                multiply.CreateInput('in2', Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.ConnectableAPI(), 'out')
                multiply.CreateOutput('out', Sdf.ValueTypeNames.Color3f)
                color.ConnectToSource(multiply.ConnectableAPI(), 'out')
            else:
                color.Set(Gf.Vec3f(*params['base_color']))
            shader.CreateOutput('out', Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput('mtlx').ConnectToSource(shader.ConnectableAPI(), 'out')
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'out')
            indices = [i for i, p in enumerate(bindings) if p == params['source_path']]
            subset = UsdGeom.Subset.CreateGeomSubset(mesh, 'Material_' + str(index), UsdGeom.Tokens.face, indices, 'materialBind', UsdGeom.Tokens.partition)
            UsdShade.MaterialBindingAPI.Apply(subset.GetPrim()).Bind(material)
            params['face_count'] = len(indices)
        camera = UsdGeom.Camera.Define(stage, '/World/Camera')
        orthographic = camera_node.evalParm('projection') == 1
        camera.CreateProjectionAttr('orthographic' if orthographic else 'perspective')
        aperture = camera_node.evalParm('orthowidth') * 10 if orthographic else camera_node.evalParm('aperture')
        camera.CreateHorizontalApertureAttr(aperture)
        camera.CreateVerticalApertureAttr(aperture * request['height'] / request['width'])
        camera.CreateFocalLengthAttr(camera_node.evalParm('focal'))
        camera.CreateClippingRangeAttr(Gf.Vec2f(camera_node.evalParm('near'), camera_node.evalParm('far')))
        camera.AddTransformOp().Set(Gf.Matrix4d(*camera_node.worldTransform().asTuple()))
        report['camera'] = {'source_path': camera_node.path(), 'projection': 'orthographic' if orthographic else 'perspective',
                            'horizontal_aperture': aperture, 'focal_length': camera_node.evalParm('focal')}
        for index, params in enumerate(report['lights']):
            p = '/World/Lights/Light_' + str(index)
            if params['type'] == 'rect':
                light = UsdLux.RectLight.Define(stage, p)
                light.CreateWidthAttr(params['width']); light.CreateHeightAttr(params['height'])
            else:
                light = UsdLux.SphereLight.Define(stage, p)
                light.CreateRadiusAttr(0.); light.CreateTreatAsPointAttr(True)
            light.CreateColorAttr(Gf.Vec3f(*params['color']))
            light.CreateIntensityAttr(params['intensity']); light.CreateExposureAttr(params['exposure'])
            light.CreateNormalizeAttr(params['normalize'])
            light.AddTransformOp().Set(Gf.Matrix4d(*params['transform']))
            light.GetPrim().SetCustomDataByKey('houdini_source', params['source_path'])
            # Native H20.5 BRAY_HdKarma_Geometry.ds declares this string property.
            light.GetPrim().CreateAttribute('primvars:karma:object:rendervisibility', Sdf.ValueTypeNames.String).Set(
                '*' if params['source_primary_visibility'] else '-primary')
        settings = UsdRender.Settings.Define(stage, '/Render/Settings')
        settings.CreateCameraRel().SetTargets([camera.GetPath()])
        settings.CreateResolutionAttr(Gf.Vec2i(request['width'], request['height'])); settings.CreatePixelAspectRatioAttr(1.)
        settings.GetPrim().CreateAttribute('karma:global:engine', Sdf.ValueTypeNames.Token).Set('xpu')
        settings.GetPrim().CreateAttribute('karma:global:abortnogpudevice', Sdf.ValueTypeNames.Bool).Set(True)
        product = UsdRender.Product.Define(stage, '/Render/Product'); product.CreateProductTypeAttr('raster')
        product.CreateProductNameAttr((folder / 'raw_$F4.exr').as_posix())
        var = UsdRender.Var.Define(stage, '/Render/Vars/Beauty')
        var.CreateDataTypeAttr('color4f'); var.CreateSourceNameAttr('C.*[LO]'); var.CreateSourceTypeAttr('lpe')
        var.GetPrim().CreateAttribute('driver:parameters:aov:name', Sdf.ValueTypeNames.String).Set('C')
        var.GetPrim().CreateAttribute('driver:parameters:aov:format', Sdf.ValueTypeNames.Token).Set('color4f')
        product.CreateOrderedVarsRel().SetTargets([var.GetPath()]); settings.CreateProductsRel().SetTargets([product.GetPath()])
        stage.SetMetadata('renderSettingsPrimPath', '/Render/Settings')
        cancellation_point(); stage.GetRootLayer().Save()
        # The worker may subsequently append diagnostics/ROI RenderSettings.
        report['base_export_usd_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        report['frame'] = frames[0]
        (folder / 'xpu-surface-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return path
    finally:
        hou.setFrame(original_frame)
