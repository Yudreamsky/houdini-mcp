"""Narrow MCP adapter for the locked captured assembly, not an arbitrary HDA API."""
import json
import hou


def is_tier_asset(node):
    return node is not None and node.type().name().startswith('workai::two_tier_snapshot::1.0.')


def managed(node):
    if not is_tier_asset(node) or not node.matchesCurrentDefinition():
        raise ValueError('Expected locked two-tier snapshot HDA')
    spec=json.loads(node.type().definition().sections()['AssemblyManifest'].contents())
    if spec.get('kind') != 'two_tier_snapshot_v1': raise ValueError('Unsupported assembly manifest')
    return spec


def inspect(node):
    managed(node)
    return dict(path=node.path(), **node.hdaModule().inspect(node))


def set_parameters(node, validated):
    managed(node)
    if any(parm.name() != 'tier_y' for parm,_,_ in validated): raise ValueError('Only tier_y is supported')
    before=inspect(node)
    if not before['passed']: raise ValueError('Current assembly failed inspection; no mutation')
    try:
        for parm,value,_ in validated: parm.set(value)
        result=inspect(node)
        if not result['passed']: raise ValueError('Assembly validation failed: '+str(result['issues']))
    except Exception as error:
        try:
            for parm,_,old in validated: parm.set(old)
            restored=inspect(node)
            if not restored['passed']: raise RuntimeError('Restored values failed inspection')
        except Exception as rollback:
            raise RuntimeError('Update failed and rollback could not be verified: '+str(rollback)) from error
        raise ValueError('Update rejected; prior parameters and geometry verified restored: '+str(error)) from error
    return dict(path=node.path(),parameters={p.name():list(p.eval()) for p,_,_ in validated},
                before={p.name():old for p,_,old in validated},inspection=result,saved=False)
