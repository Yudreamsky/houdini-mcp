"""Re-map actual named joints to the verified single-joint checker; no proxy solids."""
from . import pad_checks
from .rack_checks import bounds,TOL


def measure(parts,p):
    issues=[];results={};by={v['name']:v for v in parts};expected=set()
    for key,prefix,index,offset,z,left,right in [
        ('pipe2','pipe2_',2,p['joint_offset_2'],0,'pipe2_pipe_left','pipe2_pipe_right'),
        ('pipe3a','pipe3_',3,p['joint_offset_3'],p['spacing_23'],'pipe3_pipe_left','pipe3_pipe_middle'),
        ('pipe3b','pipe3_joint_b_',3,p['second_joint_offset_3'],p['spacing_23'],'pipe3_pipe_middle','pipe3_pipe_right')]:
        actual=[v for v in parts if v['name'].startswith(prefix) and not(key=='pipe3a' and v['name'].startswith('pipe3_joint_b_'))]
        local=[dict(v,name='pipe3_'+v['name'][len(prefix):]) for v in actual]
        q=dict(p,diameter_3=p[f'diameter_{index}'],wall_3=p[f'wall_{index}'],rise_3=p[f'rise_{index}'],spacing_23=z,joint_offset_3=offset)
        check=pad_checks.measure(local,q);results[key]=check
        issues.extend(key+': '+v for v in check['issues'])
        expected.update(f'{prefix}pad_{i:02}' for i in range(int(p['bolt_count'])))
        names=[prefix+'flange_left',prefix+'flange_right',left,right]
        if any(n not in by for n in names):issues.append(key+': Missing actual flange/pipe interface');continue
        fl,fr,pl,pr=[bounds(by[n]) for n in names]
        errors=[fl[1][0]-offset+.044,fr[0][0]-offset-.044,pl[1][0]-offset+.044,pr[0][0]-offset-.044]
        if any(abs(v)>TOL for v in errors):issues.append(key+': Actual pipe/flange endpoint mismatch')
        results[key]['endpoint_errors']=errors
    pads=[v['name'] for v in parts if v['kind']=='rubber_pad']
    if set(pads)!=expected or len(pads)!=len(expected):issues.append('Global pad coverage/identity mismatch')
    return dict(passed=not issues,issues=issues,joints=results,pad_count=len(pads),internal_flow_connection='unmodeled_at_all_three_isolation_joints')
