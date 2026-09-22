"""Inspectable parameter contracts; geometry validators remain authoritative.

Keep this outside embedded geometry sources so metadata changes do not migrate HDAs.
"""
import math
import operator

INTEGER_PARAMETERS = {'segments', 'bolt_count', 'bend_segments'}


def constraints(recipe):
    if recipe=='pipe_rack_all_pads':
        return constraints('pipe_rack_isolated')+[dict(id='all_pad_clearance_12',left='spacing_12',op='ge',terms={'diameter_1':.775,'diameter_2':.795},offset=.04,message='Clear pipe 2 pad envelope'),dict(id='all_pad_clearance_23',left='spacing_23',op='ge',terms={'diameter_2':.795,'diameter_3':.795},offset=.04,message='Clear both pad envelopes')]
    if recipe=='pipe_rack_isolated':
        return constraints('pipe_rack_repeated')+[dict(id='pad_neighbor_envelope',left='spacing_23',op='ge',terms={'diameter_2':.775,'diameter_3':.795},offset=.04,message='Clear maximum pad envelope plus 40mm')]
    if recipe=='pipe_rack_lobed':
        return constraints('pipe_rack_repeated')+[
            dict(id='lobed_body_clearance',left='spacing_23',op='ge',terms={'diameter_2':.775,'diameter_3':.82},offset=.04,message='Clear maximum lobed-body envelope plus 40mm')]

    if recipe=='pipe_rack_repeated':
        return constraints('pipe_rack_coupled')+[
            dict(id='second_joint_end',left='second_joint_offset_3',op='le',terms={'length':.5,'diameter_3':-.11},offset=-.149,message='Leave 80mm beyond conservative hardware envelope'),
            dict(id='repeated_joint_separation',left='second_joint_offset_3',op='ge',terms={'joint_offset_3':1,'diameter_3':.22},offset=.218,message='Separate two hardware envelopes by 80mm')]

    if recipe=='pipe_rack_coupled':
        return constraints('pipe_rack_reference')+[
            dict(id='red_coupling_right_end',left='joint_offset_1',op='le',terms={'length':.5,'red_shell_width':-.5},offset=-.08,message='Leave 80mm pipe beyond right shell end'),
            dict(id='red_coupling_left_end',left='joint_offset_1',op='ge',terms={'length':-.5,'red_shell_width':.5},offset=.08,message='Leave 80mm pipe beyond left shell end')]
    if recipe=='external_coupling_sample':
        return [dict(id='wall_ratio',left='wall',op='lt',right='diameter',scale=.2,offset=0,message='Wall must be less than 20 percent of diameter'),
                dict(id='cross_section_multiple',left='segments',op='multiple_of',divisor=4,message='Circular segments must be a multiple of four'),
                dict(id='coupling_right_end',left='joint_offset',op='le',terms={'length':.5,'shell_width':-.5},offset=-.08,message='Leave 80mm pipe beyond the right shell end'),
                dict(id='coupling_left_end',left='joint_offset',op='ge',terms={'length':-.5,'shell_width':.5},offset=.08,message='Leave 80mm pipe beyond the left shell end')]
    if recipe in ('pipe_rack_sample','pipe_rack_reference'):
        rules=[dict(id='cross_section_multiple',left='segments',op='multiple_of',divisor=4,message='Cross-section segments must be a multiple of four'),
               dict(id='support_coverage_length',left='support_pitch',op='le',right='length',scale=1,offset=-.24,message='Support pitch must be <= length - 0.24 m')]
        for i in (1,2,3):
            rules.extend([dict(id=f'wall_ratio_{i}',left=f'wall_{i}',op='lt',right=f'diameter_{i}',scale=.2,offset=0,message=f'Pipe {i} wall must be less than 20 percent of diameter'),
                          dict(id=f'hanger_clearance_{i}',left='hanger_height',op='ge',terms={f'diameter_{i}':1,f'rise_{i}':1},offset=.2,message=f'Hanger must clear pipe {i} diameter + rise + 0.2 m')])
        for a,b in ((1,2),(2,3)):
            rules.append(dict(id=f'flange_clearance_{a}{b}',left=f'spacing_{a}{b}',op='ge',terms={f'diameter_{a}':.775,f'diameter_{b}':.775},offset=.04,message='Horizontal spacing must clear both flange envelopes + 0.04 m'))
        return rules
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
        fields=[rule['left']]+(list(rule['terms']) if 'terms' in rule else [rule['right']] if 'right' in rule else [])
        if not set(fields)<=valid:continue
        actual=values[rule['left']]
        if rule['op']=='multiple_of':
            expected=rule['divisor'];passed=actual%expected==0
        else:
            expected=(sum(values[k]*v for k,v in rule['terms'].items()) if 'terms' in rule else values[rule['right']]*rule['scale'])+rule['offset'];passed=ops[rule['op']](actual,expected)
        if not passed:
            errors.append(dict(code=rule['id'],fields=fields,actual=actual,op=rule['op'],limit=expected,message=rule['message']))
    return errors
