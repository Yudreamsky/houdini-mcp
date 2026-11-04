"""Run experiments on a saved HIP without mutating the visible scene."""
import os
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from .storage import details,example,home,read,record,sha,stored,uid,write


def store_witness(path):
    key=uid()
    target=home()/"point_evidence"/(key+".npz")
    target.parent.mkdir(exist_ok=True,parents=True)
    shutil.copyfile(path,target)
    return key


def hip_path(value):
    aliases={"rain":("rain","Rain.hip"),"afterglow":("afterglow","Afterglow.hip")}
    path=home().joinpath("shots",*aliases[value]) if value in aliases else Path(value)
    if value=="rain" and not path.is_file():path=example("rain").parent/"Rain.hip"
    if value.startswith("sample:"):
        root=example().parent.parent
        path=(root/value.removeprefix("sample:")).resolve()
        if not path.is_relative_to(root):raise ValueError("Invalid bundled sample path")
    if not path.is_absolute() or path.suffix.lower() not in {".hip",".hiplc",".hipnc"} or not path.is_file():
        raise ValueError("Use a saved absolute HIP path or an installed rain/afterglow shot")
    return path.resolve()


def worker(req,job):
    hython=Path(os.environ.get("HOUDINI_EXE",r"C:\Program Files\Side Effects Software\Houdini 20.5.487\bin\houdini.exe")).with_name("hython.exe")
    write(job/"request.json",req)
    subprocess.run([str(hython),str(Path(__file__).with_name("sop_worker.py")),str(job)],
                   stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,check=True,env=dict(os.environ,HOUDINI_MAXTHREADS="8"))
    reply=read(job/"reply.json")
    if "gap_hint" in reply:
        from .improvements import native_gap
        receipt = native_gap(reply["gap_hint"], req, reply["error"])
        raise ValueError(f"{reply['error']} | Capability gap {receipt['gap']}, observation {receipt['observation']}. "
                         "Inspect with knowledge(key), then use improvement to propose a change and retest.")
    if "error" in reply: raise ValueError(reply["error"])
    return reply["ok"]


def variant(action,hip,node,changes,witness,frame,topic,note,key):
    prior=details(key) if key else None
    if prior and prior["kind"]!="scene_recipe":raise ValueError("Select a scene_recipe ID")
    if action=="restore" and not prior:raise ValueError("Specify the scene_recipe to restore")
    if prior:
        prev=prior["details"]
        file=hip_path(hip or prev["file"])
        if sha(file)!=prev["sha256"]:raise ValueError("The recorded HIP content changed")
        node,witness,frame,topic=prev["node"],prev["witness_path"],prev["frame"],prior["topics"][0]
    else:
        file=hip_path(hip or "rain")
    if action=="variant" and (not topic.strip() or not witness or not note.strip()):
        raise ValueError("Specify a domain topic, witness SOP and a short creative note")
    if action=="restore" and changes:raise ValueError("Use variant to change a restored recipe")
    knobs=sorted(set(changes) | (set(prev["controls"]) if prior else set()))
    dest=home()/"shots"/"rain"/"looks" if file.parent==example("rain").parent else file.parent
    target=dest/("look-"+uid()[:12]+file.suffix)
    if action=="variant":dest.mkdir(parents=True,exist_ok=True)
    req=dict(action=action,hip=str(file),node=node,changes=changes,witness=witness,frame=frame,knobs=knobs,file=str(target))
    if action=="restore" and prev.get("point_evidence"):
        req["expected_witness"]=str(stored("point_evidence",prev["point_evidence"]+".npz"))
    with tempfile.TemporaryDirectory(prefix="houdini-look-") as job:
        actual=worker(req,Path(job))
        if action=="variant":actual["point_evidence"]=store_witness(Path(job)/"witness.npz")
    if action=="restore":
        check=actual["replay_check"]
        good=actual["controls"]==prev["controls"] and actual["version"]==prev["version"] and all(
            actual["witness"][k]==prev["witness"][k] for k in ("points","primitives")) and (
            check["matched"] if check else actual["witness"]==prev["witness"])
        reuse=record("reuse",prior["title"],prior["topics"],"Reopened the saved scene and compared its controls and output SOP.",
                     {"sources":[key],"actual":actual},key,"reproduced" if good else "conflict")
        return {"verified":good,"hip":str(file),"reuse":reuse["id"],**actual}
    card=record("scene_recipe",note[:120],[topic.strip().lower()],note[:600],
                {"file":str(target),"sha256":sha(target),"node":node,"witness_path":witness,"frame":frame,**actual},key or None,"candidate")
    return {**card,"hip":str(target),**actual}


def render_frame(hip,frame,renderer,key):
    if key:
        saved=details(key)
        if saved["kind"]!="scene_recipe":raise ValueError("Select a scene_recipe ID")
        file=hip_path(hip or saved["details"]["file"])
        if sha(file)!=saved["details"]["sha256"]:raise ValueError("Scene version differs from the saved recipe")
    else:
        file=hip_path(hip or "rain")
    with tempfile.TemporaryDirectory(prefix="houdini-look-frame-") as tmp:
        job=Path(tmp)
        result=worker(dict(action="frame",hip=str(file),frame=frame,renderer=renderer),job)
        image_id=uid()
        target=home()/"images"/(image_id+".png")
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(job/result["file"],target)
    return {"image_id":image_id,"sha256":sha(target),"hip":str(file),"frame":frame,"renderer":renderer}


def run(action,hip,node,control,values,frame,renderer,topic,query,offset,limit,key,prediction="",expect_change=None):
    old=None
    if action=="replay":
        old=details(key)
        if old["kind"]!="experiment" or "request" not in old["details"]:
            raise ValueError("Select a node_lab experiment")
        req=dict(old["details"]["request"])
        hip=hip or req["hip"]
    else:
        if action not in ("inspect","nodes","sweep"):
            raise ValueError("Use nodes, inspect, sweep or replay")
        if action=="sweep" and not (2<=len(values)<=5 and len(set(values))==len(values) and topic.strip()):
            raise ValueError("Choose 2..5 distinct samples and a knowledge topic")
        if not 1<=limit<=25 or offset<0:raise ValueError("Invalid page bounds")
        req=dict(action=action,node=node,control=control,values=values,frame=frame,renderer=renderer,topic=topic,
                 query=query,offset=offset,limit=limit,prediction=prediction[:600],expect_change=expect_change)
    req["hip"]=str(hip_path(hip or "rain"))
    hip_hash=sha(Path(req["hip"])) if req["action"]=="sweep" else None
    if old and hip_hash!=old["details"]["hip_sha256"]:
        raise ValueError("The saved HIP differs from the recorded experiment")
    with tempfile.TemporaryDirectory(prefix="houdini-node-lab-") as temp:
        job=Path(temp)
        refs=[s.get("point_evidence") for s in old["details"]["samples"]] if old else []
        extra={"expected_samples":[str(stored("point_evidence",k+".npz")) for k in refs]} if refs and all(refs) else {}
        result=worker({**req,**extra},job)
        if req["action"]!="sweep":return result
        for i,sample in enumerate(result["samples"]):
            sample["point_evidence"]=store_witness(job/f"{i}.npz")
            if "file" in sample:
                source=job/sample.pop("file")
                image_id=uid()
                target=home()/"images"/(image_id+".png")
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
                sample.update(image_id=image_id,sha256=sha(target),renderer=req["renderer"])
                from PIL import Image
                with Image.open(target) as image:
                    sample["pixel_sha256"]=hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
    measures=[(s["actual"],s["metrics"],s.get("sha256")) for s in result["samples"]]
    signature={"hip":hip_hash,"node":req["node"],"control":req["control"],"frame":req["frame"],
               "version":result["baseline"]["version"],"inputs":result["baseline"]["inputs"],
               "result":[[a,m] for a,m,_ in measures]}
    match=old is not None and signature==old["details"]["repeat_signature"]
    if old and extra:
        before=old["details"]
        match=before["baseline"]["version"]==result["baseline"]["version"] and all(
            s["replay_check"]["matched"] and s["actual"]==p["actual"] and all(
                s["metrics"][k]==p["metrics"][k] for k in ("points","primitives"))
            for s,p in zip(result["samples"],before["samples"]))
    status="reproduced" if match else ("conflict" if old else "observed")
    result.update(request=req,hip_sha256=hip_hash,repeat_signature=signature)
    if match:result["series_signature"]=old["details"].get("series_signature",old["details"]["repeat_signature"])
    title=f"{result['baseline']['node_type']} / {req['control']}"
    summary=f"Frame {req['frame']}; {req['values']}; measured point positions and bounds on {req['node']}."
    tags=[req["topic"].strip().lower(),result["baseline"]["node_type"].split("/")[-1].split("::")[0]]
    card=record("experiment",title,tags,summary,result,old["id"] if old else None,status)
    first=result["samples"][0]["metrics"]
    identical_geometry=all(s["difference_from_first"]["matched"] and all(s["metrics"][k]==first[k] for k in ("points","primitives")) for s in result["samples"][1:])
    identical_images=len({s.get("pixel_sha256") for s in result["samples"]})==1
    changed=not (identical_geometry and identical_images)
    expected=req.get("expect_change")
    if (expected is None and not changed) or (expected is not None and expected!=changed):
        gap=record("gap",title+" · check response",tags,
                   "Observed change: "+str(changed)+". Check the prediction, activation conditions and selected output.",
                   {"sources":[card["id"]]},status="open")
        card["gap"]=gap["id"]
        card["review"] = "Check activation and the witness first. If a capability is missing, propose a change with improvement using this gap and experiment."
    return {**card,"samples":[{"actual":s["actual"],"metrics":s["metrics"]} for s in result["samples"]],
            "observed_change":changed,"verified_geometry_replay":match if old else None}
