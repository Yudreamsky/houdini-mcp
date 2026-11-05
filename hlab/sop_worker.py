"""Inspect or run a numeric experiment in an isolated Houdini process."""
import hashlib
import math
import os
import sys
import time
from pathlib import Path

import hou
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hlab.storage import read, sha, write

READ_ONLY_ACTIONS = {"nodes", "inspect", "animation_gap", "karma_inspect"}


def signature(node):
    geo=node.geometry()
    if geo is None or node.errors():
        raise ValueError(f"{node.path()}: {node.errors()}")
    points=geo.pointFloatAttribValuesAsString("P")
    return {"positions_sha256":hashlib.sha256(points).hexdigest(),
            "points":geo.intrinsicValue("pointcount"),"primitives":geo.intrinsicValue("primitivecount")}


def measured(node,upstream):
    stats=signature(node)
    data=np.frombuffer(node.geometry().pointFloatAttribValuesAsString("P"),dtype=np.float32).reshape(-1,3)
    if len(data):
        stats["bbox_min"]=data.min(0).tolist()
        stats["bbox_max"]=data.max(0).tolist()
        if upstream is not None and upstream.shape==data.shape:
            stats["rms_point_delta"]=float(np.sqrt(np.mean(np.sum((data-upstream)**2,axis=1))))
    return stats


def save_witness(node,path,expected=None):
    geo=node.geometry()
    arrays={a:np.frombuffer(geo.pointFloatAttribValuesAsString(a),np.float32).reshape(-1,3)
            for a in ("P","Cd") if geo.findPointAttrib(a) and geo.findPointAttrib(a).size()==3 and geo.findPointAttrib(a).dataType()==hou.attribData.Float}
    np.savez_compressed(path,**arrays)
    if not expected:return None
    return compare_arrays(arrays,expected)


def compare_arrays(arrays,expected):
    checks={}
    with np.load(expected,allow_pickle=False) as old:
        if set(old.files)!=set(arrays):return {"matched":False,"reason":"attributes changed"}
        for name,now in arrays.items():
            was=old[name]
            if was.shape!=now.shape:return {"matched":False,"reason":"array shape changed"}
            span=float(np.ptp(was,axis=0).max()) if was.size else 0.
            tolerance=1e-6 if name=="Cd" else max(1e-7,span*1e-7)
            error=float(np.max(np.abs(now-was))) if was.size else 0.
            checks[name]={"max_absolute_error":error,"tolerance":tolerance,"matched":error<=tolerance}
    return {"matched":all(c["matched"] for c in checks.values()),"attributes":checks}


def describe(parm):
    pt=parm.parmTemplate()
    info={"name":parm.name(),"label":pt.label(),"type":pt.type().name(),"disabled":parm.isDisabled(),
          "animated":bool(parm.keyframes()),"locked":parm.isLocked()}
    if isinstance(pt,(hou.FloatParmTemplate,hou.IntParmTemplate)):
        info.update(value=parm.eval(),min=pt.minValue(),max=pt.maxValue(),
                    strict_min=pt.minIsStrict(),strict_max=pt.maxIsStrict())
    else:
        info["value"]=parm.evalAsString()[:100]
    return info


def page(rows,query,offset,limit):
    query=query.casefold()
    found=[r for r in rows if query in (r.get("name","")+" "+r.get("label","")).casefold()]
    return {"total":len(found),"next_offset":offset+limit if offset+limit<len(found) else None,
            "items":found[offset:offset+limit]}


def numeric(node,name,vals,allow_toggle=False):
    parm=node.parm(name)
    if not parm: raise ValueError(f"Unknown parameter: {name}")
    pt=parm.parmTemplate()
    toggle=allow_toggle and isinstance(pt,hou.ToggleParmTemplate)
    if (not toggle and not isinstance(pt,(hou.FloatParmTemplate,hou.IntParmTemplate))) or (isinstance(pt,hou.IntParmTemplate) and pt.menuItems()) or parm.isLocked() or parm.isDisabled() or parm.keyframes() or parm.getReferencedParm()!=parm:
        raise ValueError(f"Use an enabled, unlinked, non-animated numeric parameter: {name}")
    for v in vals:
        if not math.isfinite(v) or (isinstance(pt,hou.IntParmTemplate) and not float(v).is_integer()) or (toggle and v not in (0,1)):
            raise ValueError(f"Invalid value for {parm.path()}: {v}")
        if not toggle and ((pt.minIsStrict() and v<pt.minValue()) or (pt.maxIsStrict() and v>pt.maxValue())):
            raise ValueError("Value exceeds a strict Houdini bound")
    return parm


def work(req,folder,load=True,process="fresh"):
    if req["action"] == "verify_recipe":
        from hlab.scene import load_checkpoint, state
        node = load_checkpoint(Path(req["bundle"]))
        hou.session.hr_active_path = node.path()
        hou.setFrame(req["frame"])
        return state()
    if req["action"] == "karma_sample":
        from hlab.karma_render import build_sample
        return build_sample(Path(req["target"]))
    if load:
        hou.hipFile.load(req["hip"],suppress_save_prompt=True)
    if req["action"] in READ_ONLY_ACTIONS:
        # A cached HIP must retain its entering frame, including when inspection fails.
        entering_frame = hou.frame()
        try:
            return work_loaded(req, folder, process)
        finally:
            hou.setFrame(entering_frame)
    return work_loaded(req, folder, process)


def work_loaded(req, folder, process):
    if req["action"] == "study":
        from hlab.live_study import study_file
        return study_file(req, process)
    if req["action"] == "afterglow_render":
        from afterglow_render import render
        render(Path(req["hip"]), Path(req["target"]), req["controls"], req["start"], req["end"], req["draft"], load=False)
        return {}
    if req["action"] == "mechanical_rig":
        from rig_worker import build
        return build(req)
    if req["action"] == "mechanism":
        from mechanism_worker import build
        return build(req)
    if req["action"] == "animation_gap":
        from animation_gap import measure_frames
        return measure_frames(req)
    if req["action"] == "karma_inspect":
        from hlab.karma_render import inspect
        return inspect(req)
    if req["action"] == "karma_render":
        from hlab.karma_render import render
        return render(req, folder)
    hou.setFrame(req["frame"])
    if req["action"]=="frame":
        rop=hou.node(req["renderer"])
        if not isinstance(rop,hou.RopNode) or rop.type().name()!="ifd":
            raise ValueError("Select an actual Mantra ROP")
        rop.parm("soho_foreground").set(1)
        path=folder/"frame.png"
        rop.render(frame_range=(req["frame"],req["frame"]),output_file=str(path))
        return {"frame":req["frame"],"renderer":rop.path(),"file":path.name}
    node=hou.node(req["node"])
    if not node: raise ValueError(f"Missing node {req['node']}")
    if req["action"]=="nodes":
        rows=[{"name":n.name(),"path":n.path(),"label":n.type().nameWithCategory()} for n in node.children()]
        return page(rows,req["query"],req["offset"],req["limit"])
    if not isinstance(node,hou.SopNode): raise ValueError("Select a SOP node")
    if req["action"]=="inspect":
        node.updateParmStates()
        query=req["query"].casefold()
        candidates=[p for p in node.parms() if not p.isHidden() and not isinstance(p.parmTemplate(),hou.ButtonParmTemplate)
                    and query in (p.name()+" "+p.parmTemplate().label()).casefold()]
        end=req["offset"]+req["limit"]
        return {"path":node.path(),"type":node.type().nameWithCategory(),"version":hou.applicationVersionString(),
                "total":len(candidates),"next_offset":end if end<len(candidates) else None,
                "items":[describe(p) for p in candidates[req["offset"]:end]]}
    node.updateParmStates()
    if req["action"] in ("variant","restore"):
        for name,v in req.get("changes",{}).items():
            p=numeric(node,name,[v],True)
            p.set(float(v) if isinstance(p.parmTemplate(),hou.FloatParmTemplate) else int(v))
        witness=hou.node(req["witness"])
        if not isinstance(witness,hou.SopNode):raise ValueError("Choose a SOP as the visual output witness")
        out=signature(witness)
        if witness.geometry().findPointAttrib("Cd"):
            out["color_sha256"]=hashlib.sha256(witness.geometry().pointFloatAttribValuesAsString("Cd")).hexdigest()
        observed={k:node.evalParm(k) for k in req["knobs"]}
        if req["action"]=="variant":hou.hipFile.save(req["file"],save_to_recent_files=False)
        check=save_witness(witness,folder/"witness.npz",req.get("expected_witness"))
        return {"controls":observed,"witness":out,"replay_check":check,"version":hou.applicationVersionString()}
    samples=req["values"]
    parm=numeric(node,req["control"],samples)
    pt=parm.parmTemplate()
    inputs=[signature(n) if n is not None else None for n in node.inputs()]
    first=node.inputs()[0] if node.inputs() else None
    upstream=None if first is None else np.frombuffer(first.geometry().pointFloatAttribValuesAsString("P"),dtype=np.float32).reshape(-1,3)
    original=parm.eval()
    baseline={"node_type":node.type().nameWithCategory(),"path":node.path(),"version":hou.applicationVersionString(),
              "value":original,"inputs":inputs,"frame":req["frame"],"metrics":measured(node,upstream)}
    rop=hou.node(req["renderer"]) if req["renderer"] else None
    if req["renderer"] and (not isinstance(rop,hou.RopNode) or rop.type().name()!="ifd"):
        raise ValueError("For optical evidence select a Mantra ROP, or omit renderer for a geometry-only run")
    results=[]
    for i,v in enumerate(samples):
        parm.set(int(v) if isinstance(pt,hou.IntParmTemplate) else v)
        result={"frame":req["frame"],"actual":parm.eval(),"metrics":measured(node,upstream)}
        refs=req.get("expected_samples",[])
        result["replay_check"]=save_witness(node,folder/f"{i}.npz",refs[i] if refs else None)
        if i:
            with np.load(folder/f"{i}.npz",allow_pickle=False) as current:
                result["difference_from_first"]=compare_arrays(current,folder/"0.npz")
        if rop:
            path=folder/f"{i}.png"
            rop.parm("soho_foreground").set(1)
            rop.render(frame_range=(req["frame"],req["frame"]),output_file=str(path))
            if not path.is_file():raise RuntimeError("Missing Mantra evidence frame")
            result["file"]=path.name
        results.append(result)
    parm.set(original)
    if measured(node,upstream)!=baseline["metrics"]:raise RuntimeError("Baseline did not reproduce after the sweep")
    return {"baseline":baseline,"control":req["control"],"samples":results,"baseline_restored":True}


def execute(folder, process, cached=None):
    request = read(folder/"request.json")
    try:
        signature = None
        if process == "warm":
            hip = Path(request["hip"])
            signature = (str(hip), sha(hip))
            if signature != cached:
                hou.hipFile.clear(suppress_save_prompt=True)
        result = work(request, folder, load=signature is None or signature != cached, process=process)
        result.update(process=process, process_pid=os.getpid(), houdini_version=hou.applicationVersionString())
        result = {"ok": result}
        # Sweeps and renders can leave edited parameters or a render ROP, even after a successful result.
        cached = signature if request["action"] in READ_ONLY_ACTIONS else None
    except Exception as exc:
        cached = None
        result={"error":f"{type(exc).__name__}: {exc}"}
        if hasattr(exc, "gap_hint"):
            result["gap_hint"] = exc.gap_hint
    write(folder/"reply.json",result)
    return cached


def serve(mailbox, idle):
    cached = None
    quiet_since = time.monotonic()
    slot = mailbox/"request.json"
    while time.monotonic() - quiet_since < idle:
        if not slot.exists():
            time.sleep(.025)
            continue
        message = read(slot)
        slot.unlink()
        folder = Path(message["folder"])
        if time.time() > message["deadline"]:
            write(folder/"reply.json", {"error": "Background request expired before execution"})
        else:
            cached = execute(folder, "warm", cached)
        quiet_since = time.monotonic()


if __name__=="__main__":
    if sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]), float(sys.argv[3]))
    else:
        execute(Path(sys.argv[1]), "fresh")
