"""Houdini-side, deliberately narrow emissive-map to USD/MaterialX adapter."""
import math
from pathlib import Path
import hou

ASSET_TYPE = 'workai::indonesia_glow_map::2.0'
ADAPTER_VERSION = 1


def validate_map(request, camera):
    asset = hou.node(request.get('asset_path', ''))
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise ValueError('Karma XPU adapter only supports ' + ASSET_TYPE)
    if camera is None or camera.evalParm('projection') != 1 or camera.evalParm('aspect') != 1:
        raise ValueError('Karma map preview requires an orthographic, square-pixel camera')
    material = asset.node('materials/emission')
    if material is None or not material.type().name().startswith('principledshader'):
        raise ValueError('Unsupported map material; expected the validated emissive material')
    expected = {'diffuselevel': 0, 'emitint': 1, 'emitcolor_usePointColor': 1,
                'emitcolor_useTexture': 0, 'basecolor_useTexture': 0, 'emitillum': 0}
    for key, value in expected.items():
        if material.evalParm(key) != value:
            raise ValueError('Unsupported emissive material setting: ' + key)
    if tuple(material.parmTuple('emitcolor').eval()) != (1.0, 1.0, 1.0):
        raise ValueError('Unsupported emission tint; expected white multiplied by primitive Cd')
    geometry = asset.geometry()
    if geometry is None or asset.errors() or geometry.findPrimAttrib('Cd') is None:
        raise ValueError('Map geometry requires primitive Cd and must cook without errors')
    if any(p.type() != hou.primType.Polygon or p.attribValue('shop_materialpath') != material.path() for p in geometry.prims()):
        raise ValueError('Only polygons assigned to the validated emission material are supported')
    return asset


def export_map(folder, request, frames, cancellation_point):
    from pxr import Usd, UsdGeom, UsdShade, UsdRender, Sdf, Gf, Vt
    rop = hou.node(request['rop_path'])
    camera_node = hou.node(rop.evalParm('camera'))
    asset = validate_map(request, camera_node)
    path = folder / 'render.usdc'
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetStartTimeCode(min(frames)); stage.SetEndTimeCode(max(frames))
    stage.SetFramesPerSecond(hou.fps()); stage.SetTimeCodesPerSecond(hou.fps())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, '/World')
    mesh = UsdGeom.Mesh.Define(stage, '/World/Map')
    mesh.CreateSubdivisionSchemeAttr('none'); mesh.CreateDoubleSidedAttr(True)
    transform = mesh.AddTransformOp()
    cd = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('Cd', Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.uniform)
    camera = UsdGeom.Camera.Define(stage, '/World/Camera')
    camera.CreateProjectionAttr('orthographic')
    camera_transform = camera.AddTransformOp()
    for frame in frames:
        cancellation_point(); hou.setFrame(frame)
        validate_map(request, camera_node)
        geometry = asset.geometry()
        points = [tuple(p.position()) for p in geometry.points()]
        colors = [p.attribValue('Cd') for p in geometry.prims()]
        if any(not math.isfinite(v) for item in points + colors for v in item):
            raise ValueError('Nonfinite map positions or colors')
        mesh.CreatePointsAttr().Set(Vt.Vec3fArray(points), frame)
        mesh.CreateFaceVertexCountsAttr().Set([len(p.vertices()) for p in geometry.prims()], frame)
        mesh.CreateFaceVertexIndicesAttr().Set([v.point().number() for p in geometry.prims() for v in p.vertices()], frame)
        cd.Set(Vt.Vec3fArray(colors), frame)
        transform.Set(Gf.Matrix4d(*asset.parent().worldTransform().asTuple()), frame)
        bbox = geometry.boundingBox()
        mesh.CreateExtentAttr().Set([Gf.Vec3f(*bbox.minvec()), Gf.Vec3f(*bbox.maxvec())], frame)
        camera.CreateHorizontalApertureAttr().Set(camera_node.evalParm('orthowidth') * 10, frame)
        camera.CreateVerticalApertureAttr().Set(camera_node.evalParm('orthowidth') * 10 * request['height'] / request['width'], frame)
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(camera_node.evalParm('near'), camera_node.evalParm('far')), frame)
        camera_transform.Set(Gf.Matrix4d(*camera_node.worldTransform().asTuple()), frame)
    material = UsdShade.Material.Define(stage, '/World/Looks/Emission')
    shader = UsdShade.Shader.Define(stage, '/World/Looks/Emission/Surface')
    shader.CreateIdAttr('ND_surface_unlit')
    shader.CreateInput('emission', Sdf.ValueTypeNames.Float).Set(1.0)
    reader = UsdShade.Shader.Define(stage, '/World/Looks/Emission/Color')
    reader.CreateIdAttr('ND_geompropvalue_color3')
    reader.CreateInput('geomprop', Sdf.ValueTypeNames.String).Set('Cd')
    reader.CreateOutput('out', Sdf.ValueTypeNames.Color3f)
    shader.CreateInput('emission_color', Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.ConnectableAPI(), 'out')
    shader.CreateOutput('out', Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput('mtlx').ConnectToSource(shader.ConnectableAPI(), 'out')
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'out')
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    settings = UsdRender.Settings.Define(stage, '/Render/Settings')
    settings.CreateCameraRel().SetTargets([camera.GetPath()])
    settings.CreateResolutionAttr(Gf.Vec2i(request['width'], request['height']))
    settings.CreatePixelAspectRatioAttr(1.0)
    settings.GetPrim().CreateAttribute('karma:global:engine', Sdf.ValueTypeNames.Token).Set('xpu')
    settings.GetPrim().CreateAttribute('karma:global:abortnogpudevice', Sdf.ValueTypeNames.Bool).Set(True)
    product = UsdRender.Product.Define(stage, '/Render/Product')
    product.CreateProductTypeAttr('raster')
    product.CreateProductNameAttr((folder / 'raw_$F4.exr').as_posix())
    var = UsdRender.Var.Define(stage, '/Render/Vars/Beauty')
    var.CreateDataTypeAttr('color4f'); var.CreateSourceNameAttr('C.*[LO]'); var.CreateSourceTypeAttr('lpe')
    var.GetPrim().CreateAttribute('driver:parameters:aov:name', Sdf.ValueTypeNames.String).Set('C')
    var.GetPrim().CreateAttribute('driver:parameters:aov:format', Sdf.ValueTypeNames.Token).Set('color4f')
    product.CreateOrderedVarsRel().SetTargets([var.GetPath()]); settings.CreateProductsRel().SetTargets([product.GetPath()])
    stage.SetMetadata('renderSettingsPrimPath', '/Render/Settings')
    stage.GetRootLayer().Save()
    return path
