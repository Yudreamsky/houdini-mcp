"""Houdini-side optical comparison. Reads the same HIP and cached volumes for every take."""
import argparse
import json
from pathlib import Path

import hou


def render(hip, target, controls, start, end, draft=False):
    hou.hipFile.load(str(hip),suppress_save_prompt=True)
    hou.node("/obj/DIRECTION").setParms(controls)
    rop=hou.node("/out/RELIGHT")
    if draft:
        hou.node("/obj/CAM").setParms({"resx":480,"resy":270})
        rop.setParms({"vm_samplesx":1,"vm_samplesy":1,"vm_maxraysamples":2})
    rop.parm("vm_picture").set(target.as_posix()+"/$F4.exr")
    target.mkdir(parents=True,exist_ok=True)
    rop.render(frame_range=(start,end),verbose=True)
    if rop.errors():
        raise RuntimeError(rop.errors())


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("hip",type=Path)
    p.add_argument("target",type=Path)
    p.add_argument("controls")
    p.add_argument("start",type=int)
    p.add_argument("end",type=int)
    p.add_argument("--draft",action="store_true")
    a=p.parse_args()
    render(a.hip.resolve(),a.target.resolve(),json.loads(a.controls),a.start,a.end,a.draft)
