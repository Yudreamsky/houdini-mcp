"""Small Houdini-side operations, imported lazily by the existing bridge."""
import math
import hou

def set_parameters(path, values):
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
        validated.append((parm,value,list(parm.eval())))
    # Validate the complete request before changing any parameter.
    try:
        for parm,value,_ in validated:parm.set(value)
    except Exception:
        for parm,_,old in validated:parm.set(old)
        raise
    return {'path':node.path(),'parameters':{parm.name():list(parm.eval()) for parm,_,_ in validated},'saved':False}
