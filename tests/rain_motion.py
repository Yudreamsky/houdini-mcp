"""Check impact order, finite propagation, superposition and airborne drop motion in the saved HIP."""
import json
import math
import sys
from pathlib import Path

import hou
import numpy as np


def points(node):
    return np.frombuffer(node.geometry().pointFloatAttribValuesAsString("P"),np.float32).reshape(-1,3)


def check(hip):
    hou.hipFile.load(str(hip),suppress_save_prompt=True)
    n=lambda name:hou.node("/obj/RAIN/"+name)
    grid=points(n("Undisturbed_water")).copy()
    centre=np.array([-1.10,.30])
    radii=np.linalg.norm(grid[:,[0,2]]-centre,axis=1)
    y_before=[]
    for f in (5,7,9):
        hou.setFrame(f)
        assert np.max(np.abs(points(n("Propagate_5"))[:,1]))==0
        q=points(hou.node("/obj/DROPS/Rain_and_rebound"))
        y_before.append(float(q[np.argmin(np.linalg.norm(q[:,[0,2]]-centre,axis=1)),1]))
    assert y_before[0]>y_before[1]>y_before[2]>0
    hou.setFrame(20)
    y=points(n("Propagate_5"))[:,1].copy()
    k=2*math.pi/.54
    omega=math.sqrt(981*k+72*k**3)
    group_speed=(981+216*k*k)/(2*omega)*.055
    front=group_speed*(20-10)/24
    outside=float(np.abs(y[radii>front+.25]).max())
    assert outside<1e-7 and float(np.max(np.abs(y)))>.001
    hou.setFrame(38)
    first=points(n("Propagate_1"))[:,1].copy()
    summed=points(n("Propagate_2"))[:,1].copy()
    overlap=int(((np.abs(first)>.001)&(np.abs(summed-first)>.001)).sum())
    assert overlap>10
    return {"first_contact_frame":10,"first_drop_height_cm_frames_5_7_9":y_before,
            "group_speed_cm_per_playback_second":group_speed,"front_radius_cm_at_20":front,
            "max_displacement_beyond_front_cm":outside,"overlap_points_at_38":overlap,
            "units":"centimetres, 24 fps, physical time factor 0.055"}


if __name__=="__main__":
    print(json.dumps(check(Path(sys.argv[1]).resolve()),indent=2))
