"""Inspectable parameter contracts; geometry validators remain authoritative.

Keep this outside embedded geometry sources so metadata changes do not migrate HDAs.
"""
import math
import operator

INTEGER_PARAMETERS = {'segments', 'bolt_count', 'bend_segments'}


def constraints(recipe):
    if recipe not in ('pipe_support_sample', 'pipe_elbow_sample'):
        raise ValueError('Unsupported recipe: '+str(recipe))
    rules = [
        dict(id='wall_ratio', left='wall', op='lt', right='diameter', scale=.2, offset=0,
             message='Wall must be less than 20 percent of diameter'),
        dict(id='hanger_clearance', left='hanger_height', op='ge', right='diameter', scale=1, offset=.2,
             message='Hanger height must be at least diameter + 0.2 m'),
        dict(id='cross_section_multiple', left='segments', op='multiple_of', divisor=4,
             message='Cross-section segments must be a multiple of four'),
    ]
    lengths=['length'] if recipe=='pipe_support_sample' else ['inlet_length','outlet_length']
    for length in lengths:
        rules.append(dict(id='support_coverage_'+length, left='support_pitch', op='le', right=length,
                          scale=1, offset=-.24, message='Support pitch must be <= '+length+' - 0.24 m'))
    if recipe=='pipe_elbow_sample':
        rules.append(dict(id='bend_radius_ratio', left='bend_radius', op='ge', right='diameter', scale=1.5, offset=0,
                          message='Centerline bend radius must be at least 1.5 times diameter (recipe constraint)'))
    return rules


def parameter_schema(parameters):
    return {key:dict(default=value[0], min=value[1], max=value[2], label=value[3],
                     type='integer' if key in INTEGER_PARAMETERS else 'number') for key,value in parameters.items()}


def violations(recipe, definitions, values):
    errors=[]; valid=set()
    for key in sorted(set(values)-set(definitions)):
        errors.append(dict(code='unknown_parameter', fields=[key], message='Unknown parameter: '+key))
    for key,(_,lo,hi,_) in definitions.items():
        value=values.get(key)
        if type(value) not in (int,float) or not math.isfinite(value):
            errors.append(dict(code='finite_number_required',fields=[key],message='Expected finite numeric value: '+key))
        elif not lo<=value<=hi:
            errors.append(dict(code='range',fields=[key],actual=value,min=lo,max=hi,message='Value outside allowed bounds: '+key))
        elif key in INTEGER_PARAMETERS and int(value)!=value:
            errors.append(dict(code='integer_required',fields=[key],actual=value,message='Expected integer: '+key))
        else:valid.add(key)
    ops={'lt':operator.lt,'le':operator.le,'ge':operator.ge}
    for rule in constraints(recipe):
        fields=[rule['left']]+([rule['right']] if 'right' in rule else [])
        if not set(fields)<=valid:continue
        actual=values[rule['left']]
        if rule['op']=='multiple_of':
            expected=rule['divisor'];passed=actual%expected==0
        else:
            expected=values[rule['right']]*rule['scale']+rule['offset'];passed=ops[rule['op']](actual,expected)
        if not passed:
            errors.append(dict(code=rule['id'],fields=fields,actual=actual,op=rule['op'],limit=expected,message=rule['message']))
    return errors
