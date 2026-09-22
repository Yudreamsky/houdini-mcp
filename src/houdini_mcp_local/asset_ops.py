"""Small Houdini-side operations, imported lazily by the existing bridge."""
import math
import hou

def validate_parameters(path, values):
    node=hou.node(path)
    if node is None: raise ValueError('Node does not exist: '+path)
    validated=[]
    for name,value in values.items():
        parm=node.parmTuple(name)
        if parm is None: raise ValueError('Unknown parameter: '+name)
        if parm.parmTemplate().type() not in (hou.parmTemplateType.Float,hou.parmTemplateType.Int,hou.parmTemplateType.Toggle):
            raise ValueError('Only numeric parameters are supported: '+name)
        value=value if isinstance(value,list) else [value]
        if len(value)!=len(parm): raise ValueError('Wrong tuple size: '+name)
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):raise ValueError('Expected finite numeric values: '+name)
        if any(p.keyframes() for p in parm):raise ValueError('Animated parameter must be edited explicitly: '+name)
        if any(p.isLocked() or p.isDisabled() for p in parm):raise ValueError('Locked or disabled parameter: '+name)
        template=parm.parmTemplate()
        if template.type() in (hou.parmTemplateType.Int,hou.parmTemplateType.Toggle) and any(int(v)!=v for v in value):raise ValueError('Expected integer values: '+name)
        if template.type()==hou.parmTemplateType.Toggle and any(v not in (0,1) for v in value):raise ValueError('Toggle must be 0 or 1: '+name)
        if hasattr(template,'minIsStrict') and template.minIsStrict() and any(v<template.minValue() for v in value):raise ValueError('Below strict minimum: '+name)
        if hasattr(template,'maxIsStrict') and template.maxIsStrict() and any(v>template.maxValue() for v in value):raise ValueError('Above strict maximum: '+name)
        validated.append((parm,value,list(parm.eval())))
    return validated


def set_parameters(path, values):
    validated=validate_parameters(path,values)
    from . import tier_asset_ops
    if tier_asset_ops.is_tier_asset(hou.node(path)):
        return tier_asset_ops.set_parameters(hou.node(path),validated)
    # Validate the complete request before changing any parameter.
    try:
        for parm,value,_ in validated:parm.set(value)
    except Exception:
        for parm,_,old in validated:parm.set(old)
        raise
    return {'path':path,'parameters':{parm.name():list(parm.eval()) for parm,_,_ in validated},'before':{parm.name():old for parm,_,old in validated},'saved':False}


def get_schema(path):
    node=hou.node(path)
    if node is None:raise ValueError('Node does not exist: '+path)
    parameters=[]
    for parm in node.parmTuples():
        t=parm.parmTemplate()
        if t.type() not in (hou.parmTemplateType.Float,hou.parmTemplateType.Int,hou.parmTemplateType.Toggle):continue
        entry={'name':parm.name(),'label':t.label(),'type':str(t.type()),'components':len(parm),'value':list(parm.eval()),'default':list(t.defaultValue()) if isinstance(t.defaultValue(),tuple) else [t.defaultValue()], 'animated':any(p.keyframes() for p in parm),'locked':any(p.isLocked() for p in parm),'disabled':any(p.isDisabled() for p in parm),'tags':t.tags(),'conditionals':{str(k):v for k,v in t.conditionals().items()}}
        if hasattr(t,'minValue'):entry.update(min=t.minValue(),max=t.maxValue(),min_strict=t.minIsStrict(),max_strict=t.maxIsStrict())
        if hasattr(t,'menuItems'):entry.update(menu_items=list(t.menuItems()),menu_labels=list(t.menuLabels()))
        parameters.append(entry)
    result={'path':path,'node_type':node.type().nameWithCategory(),'parameters':parameters}
    from . import tier_asset_ops
    if tier_asset_ops.is_tier_asset(node):
        spec=tier_asset_ops.managed(node)
        result['assembly']={k:spec[k] for k in ('kind','base_height','height_min','height_max','moving','stations','interpretation')}
    return result


def preset(action, name='', path='', overwrite=False):
    import hashlib,json,re
    from pathlib import Path
    from .io_utils import atomic_json
    from .locking import file_lock
    root=Path(__file__).resolve().parents[2]/'.runtime'/'presets'
    root.mkdir(parents=True,exist_ok=True)
    if action=='list':return {'presets':[p.stem for p in sorted(root.glob('*.json'))]}
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise ValueError('Preset name must contain 1-64 letters, digits, underscores or hyphens')
    destination=root/(name+'.json')
    schema=get_schema(path)
    signature=hashlib.sha256(json.dumps([(p['name'],p['type'],p['components']) for p in schema['parameters']]).encode()).hexdigest()
    with file_lock(root/'.lock'):
        if action=='capture':
            if destination.exists() and not overwrite:raise FileExistsError('Preset already exists; explicit overwrite required')
            values={p['name']:p['value'] for p in schema['parameters'] if not(p['animated'] or p['locked'] or p['disabled'])}
            atomic_json(destination,{'node_type':schema['node_type'],'schema_sha256':signature,'parameters':values})
            return {'name':name,'captured_parameters':len(values),'skipped_parameters':[p['name'] for p in schema['parameters'] if p['name'] not in values]}
        if action=='apply':
            data=json.loads(destination.read_text(encoding='utf-8'))
            if data['node_type']!=schema['node_type'] or data['schema_sha256']!=signature:raise ValueError('Preset asset type or parameter schema mismatch')
            return {'name':name,**set_parameters(path,data['parameters'])}
    raise ValueError('Action must be list, capture or apply')
