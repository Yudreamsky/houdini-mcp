"""Editable groups and evidence for the residual-smoke shot."""
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .bridge import call_in
from .storage import details, home, read, record, sha, uid, write

LIMITS = {"smoke":(0,4),"flash":(0,3),"duration":(.25,20)}


def folder():
    return home()/"shots"/"afterglow"


def source(key, fingerprint):
    item = details(key)
    if item["kind"]!="shot" or item["details"]["asset"]!=fingerprint:
        raise ValueError("Select a version of this Afterglow HIP and cache")
    return item["details"]["controls"]


def setup():
    path = folder()
    if not (path/"cache.json").is_file():
        raise ValueError("Build the Afterglow shot first")
    return {"hip_sha":sha(path/"Afterglow.hip"),"cache_sha":read(path/"cache.json")["sha256"]}


def current():
    p=folder()/"current.json"
    return read(p)["id"] if p.exists() else None


def live(**args):
    return call_in(window_dir(folder()),"afterglow_live",**args)


def window_dir(path):
    return path/"windows"/sha(path/"Afterglow.hip")[:12]


def revise(changes, note, base="", smoke_from="", flash_from=""):
    asset=setup()
    before=live()
    parent=base or current()
    controls=dict(source(base,asset) if base else before["controls"])
    if smoke_from:
        controls["smoke"]=source(smoke_from,asset)["smoke"]
    if flash_from:
        previous=source(flash_from,asset)
        controls.update({k:previous[k] for k in ("flash","duration")})
    for name,value in changes.items():
        if name not in LIMITS or not math.isfinite(value) or not LIMITS[name][0]<=value<=LIMITS[name][1]:
            raise ValueError(f"Unsupported control or value: {name}={value}. Bounds: {LIMITS}")
        controls[name]=value
    actual=live(changes=controls)
    if any(abs(actual["controls"][k]-v)>1e-4 for k,v in controls.items()):
        raise RuntimeError("Live controls did not match the proposed revision")
    card=record("shot","第二发照亮残烟",["afterglow","fireworks","smoke","lighting"],note[:600],
                {"asset":asset,"controls":actual["controls"],"smoke_from":smoke_from or None,
                 "flash_from":flash_from or None,"edited":changes,"frame":actual["frame"]},parent,"candidate")
    write(folder()/"current.json",{"id":card["id"]})
    return {**card,"controls":actual["controls"]}


def develop_image(path):
    # Mantra beauty RGB is scene-linear, already associated with volume coverage.
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR","1")
    import cv2
    import numpy as np
    from PIL import Image
    pixels=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
    if pixels is None or pixels.ndim!=3 or pixels.shape[2]!=4:
        raise ValueError("Expected a Mantra RGBA EXR")
    linear=np.maximum(0,pixels[:,:,[2,1,0]]) + np.array([.0013,.002,.004])*(1-pixels[:,:,3,None])
    tone=(1-np.exp(-linear*1.4))**(1/2.2)
    return Image.fromarray(np.uint8(255*np.clip(tone,0,1)))


def take(key, start, end, draft=False):
    if not 1<=start<=end<=79 or end-start>29:
        raise ValueError("Choose at most 30 consecutive frames in 1..79")
    asset=setup()
    controls=source(key,asset) if key else live()["controls"]
    target=folder()/"renders"/uid()
    from .sop_lab import worker
    with tempfile.TemporaryDirectory(prefix="houdini-afterglow-") as job:
        execution = worker(dict(action="afterglow_render", hip=str(folder()/"Afterglow.hip"),
                                target=str(target),controls=controls,start=start,end=end,draft=draft),Path(job))
    info={"start":start,"end":end,"key":key or None,"controls":controls,"asset":asset,**execution}
    # Decode native EXRs outside the Windows MCP stdio process (OpenCV loads native DLLs).
    subprocess.run([sys.executable,"-m","hlab.afterglow",str(target),str(start),str(end)],
                   cwd=Path(__file__).resolve().parents[1],stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,check=True)
    from PIL import Image
    preview=target/"preview.png"
    path=target/"review.gif" if end>start else target/f"{start:04d}.exr"
    with Image.open(preview) as im:
        return {**info,"path":str(path),"fps":24},im.copy()


def grade(target,start,end):
    from PIL import Image
    if start==end:
        develop_image(target/f"{start:04d}.exr").save(target/"preview.png")
        return
    images=[develop_image(target/f"{i:04d}.exr") for i in range(start,end+1)]
    path=target/"review.gif"
    durations=[10*(round((i+1)*100/24)-round(i*100/24)) for i in range(len(images))]
    images[0].save(path,save_all=True,append_images=images[1:],duration=durations,loop=0)
    w,h=images[0].size
    sheet=Image.new("RGB",(w*3,h))
    for i,n in enumerate((0,len(images)//2,len(images)-1)):
        sheet.paste(images[n],(i*w,0))
    sheet.save(target/"preview.png")


if __name__=="__main__":
    grade(Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]))
