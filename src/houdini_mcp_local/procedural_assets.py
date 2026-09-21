"""Houdini operations for a versioned procedural recipe and owned instances."""
import hashlib
import importlib
import json
import re
from pathlib import Path
import hou
from . import sample_geometry
from .asset_ops import validate_parameters
from . import recipe_contract

ROOT = Path(__file__).resolve().parents[2]
RECIPE = 'pipe_support_sample'
RECIPES = (RECIPE, 'pipe_elbow_sample')


def source(recipe):
    importlib.reload(sample_geometry)
    code=Path(sample_geometry.__file__).read_text(encoding='utf-8')
    if recipe==RECIPE: return sample_geometry,code
    if recipe!='pipe_elbow_sample': raise ValueError('Unsupported recipe: '+recipe)
    from . import elbow_geometry
    importlib.reload(elbow_geometry)
    # Embed the unchanged straight algorithm in a separate namespace so its
    # parameters/build functions cannot be rebound by the routed recipe.
    prefix='import types\nbase=types.ModuleType("embedded_straight_recipe")\nexec('+repr(code)+',base.__dict__)\n'
    return elbow_geometry,prefix+Path(elbow_geometry.__file__).read_text(encoding='utf-8')


def catalog():
    importlib.reload(recipe_contract)
    recipes=[]
    for recipe in RECIPES:
        module,_=source(recipe)
        recipes.append({'id':recipe,'version':'1.0','units':'metres',
                        'scope':'Illustrative pipe joint/support sample'+(' with one horizontal 90 degree elbow' if recipe!=RECIPE else '')+'; not an engineering design',
                        'parameters':recipe_contract.parameter_schema(module.PARAMETERS),
                        'constraints':recipe_contract.constraints(recipe),
                        'structured_inputs':False})
    return {'recipes':recipes,'library_mode':'Self-contained HDA compiled from versioned recipe source'}


def definition(recipe=RECIPE):
    module,code=source(recipe)
    digest=hashlib.sha256(code.encode()).hexdigest()
    typename='workai::'+recipe+'::1.0.'+digest[:12]
    folder=ROOT/'.runtime'/'asset-library'; folder.mkdir(parents=True,exist_ok=True)
    library=folder/(typename.replace('::','_')+'.hda')
    if not library.exists():
        parent=hou.node('/obj').createNode('geo',node_name='__workai_build_hda',run_init_scripts=False)
        try:
            sub=parent.createNode('subnet','sample')
            python=sub.createNode('python','build_geometry')
            python.parm('python').set('hou.pwd().parent().hdaModule().cook(hou.pwd())')
            out=sub.createNode('null','OUT'); out.setInput(0,python); out.setDisplayFlag(True); out.setRenderFlag(True)
            asset=sub.createDigitalAsset(name=typename,hda_file_name=str(library),description='WORKAI Pipe Support Sample',min_num_inputs=0,max_num_inputs=0)
            group=hou.ParmTemplateGroup()
            for key,(default,lo,hi,label) in module.PARAMETERS.items():
                cls=hou.IntParmTemplate if key in ('bolt_count','segments','bend_segments') else hou.FloatParmTemplate
                group.append(cls(key,label,1,default_value=(default,),min=lo,max=hi,min_is_strict=True,max_is_strict=True))
            d=asset.type().definition(); d.setParmTemplateGroup(group); d.addSection('PythonModule',code)
            d.addSection('Help','Metre-based visual sample. Values are illustrative, not derived measurements or code-compliant specifications. OUT carries name, part_type, Cd and sample_spec. Embedded PythonModule needs only hou and Python standard library.')
            asset.matchCurrentDefinition()
            asset.geometry()
            if asset.errors(): raise RuntimeError(str(asset.errors()))
        except Exception:
            # Do not leave a half-built library as an apparently usable recipe.
            if library.exists():
                hou.hda.uninstallFile(str(library)); library.unlink()
            raise
        finally:
            parent.destroy()
    definitions=hou.hda.definitionsInFile(str(library))
    if len(definitions)!=1 or definitions[0].nodeTypeName()!=typename or definitions[0].sections()['PythonModule'].contents()!=code:
        raise ValueError('Cached HDA does not match the recipe source; preserve it for inspection')
    hou.hda.installFile(str(library))
    for d in hou.hda.definitionsInFile(str(library)): d.setIsPreferred(True)
    return typename,library,digest


def managed(path):
    node=hou.node(path)
    if not isinstance(node,hou.SopNode) or node.userData('workai_recipe') not in RECIPES:
        raise ValueError('Expected an owned procedural sample SOP')
    if not node.matchesCurrentDefinition():
        raise ValueError('Asset contents are unlocked; inspect manual changes before using managed updates')
    return node


class InvalidParameters(ValueError):
    def __init__(self, errors):
        self.errors=errors
        super().__init__(json.dumps(errors))


def prepare(instance_id, parameters=None, recipe=None):
    """Shared read-only resolution/validation. Never builds, installs or cooks an HDA."""
    if not isinstance(instance_id,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',instance_id):
        raise ValueError('instance_id must start with a letter and use at most 64 letters/digits/_/-')
    if parameters is not None and not isinstance(parameters,dict):raise ValueError('parameters must be an object')
    name='workai_'+hashlib.sha256(instance_id.encode()).hexdigest()[:16]
    parent=hou.node('/obj/'+name); existing=parent is not None;node=None
    if existing:
        if parent.userData('workai_instance_id')!=instance_id: raise ValueError('Target object is not owned by this instance')
        node=managed(parent.path()+'/asset')
        stored_recipe=node.userData('workai_recipe')
        if recipe is not None and stored_recipe!=recipe: raise ValueError('Instance recipe differs; use a new ID rather than replacing its recipe')
        recipe=stored_recipe
    elif recipe is None:recipe=RECIPE
    module,code=source(recipe)
    if existing:
        before={k:node.evalParm(k) for k in module.PARAMETERS}
    else:
        before={}
    values={k:v[0] for k,v in module.PARAMETERS.items()};values.update(before);values.update(parameters or {})
    importlib.reload(recipe_contract)
    errors=recipe_contract.violations(recipe,module.PARAMETERS,values)
    if errors:raise InvalidParameters(errors)
    values=module.validate(values)
    digest=hashlib.sha256(code.encode()).hexdigest()
    if existing:
        validate_parameters(node.path(),values)
        # Never silently migrate an instance to a changed recipe implementation.
        if node.userData('workai_recipe_sha256')!=digest: raise ValueError('Recipe version changed; create a new instance for explicit migration')
    return dict(name=name,parent=parent,node=node,existing=existing,recipe=recipe,before=before,values=values,digest=digest)


def preflight(instance_id, parameters=None, recipe=None):
    try:
        plan=prepare(instance_id,parameters,recipe)
    except InvalidParameters as exc:
        return dict(ready=False,instance_id=instance_id,errors=exc.errors,scene_modified=False)
    except ValueError as exc:
        return dict(ready=False,instance_id=instance_id,errors=[dict(code='instance_or_channel_guard',message=str(exc))],scene_modified=False)
    return dict(ready=True,instance_id=instance_id,recipe=plan['recipe'],path='/obj/'+plan['name']+'/asset',
                will_create=not plan['existing'],would_change=plan['before']!=plan['values'],
                before=plan['before'],parameters=plan['values'],recipe_sha256=plan['digest'],
                constraints=recipe_contract.constraints(plan['recipe']),errors=[],scene_modified=False,
                scope='Input/instance/channel validation only; geometry cook and inspection occur on upsert. Revalidated at write time.')


def upsert(instance_id, parameters=None, recipe=None):
    plan=prepare(instance_id,parameters,recipe)
    name,parent,node,existing,recipe,before,values,digest=(plan[k] for k in ('name','parent','node','existing','recipe','before','values','digest'))
    if existing:library=Path(node.type().definition().libraryFilePath())
    else:
        typename,library,digest=definition(recipe)
        parent=hou.node('/obj').createNode('geo',node_name=name,run_init_scripts=False)
        try:
            parent.setUserData('workai_instance_id',instance_id)
            node=parent.createNode(typename,'asset')
            node.setUserData('workai_recipe',recipe); node.setUserData('workai_recipe_sha256',digest)
            node.setUserData('workai_instance_id',instance_id)
            node.setDisplayFlag(True); node.setRenderFlag(True)
        except Exception:
            parent.destroy()
            raise
    try:
        if not existing or before!=values:
            for key,value in values.items(): node.parm(key).set(value)
            node.cook(force=True)
        if node.errors(): raise RuntimeError(str(node.errors()))
        from . import sample_inspection
        importlib.reload(sample_inspection)
        check=sample_inspection.inspect(node.path())
        if not check['passed']: raise RuntimeError('Sample checks failed: '+json.dumps(check['issues']))
    except Exception:
        if existing:
            for key,value in before.items(): node.parm(key).set(value)
            node.cook(force=True)
        else: parent.destroy()
        raise
    return dict(instance_id=instance_id,recipe=recipe,path=node.path(),object_path=parent.path(),created=not existing,
                changed=before!=values,parameters=values,before=before,library=str(library),
                recipe_sha256=digest,check=check,saved=False)
