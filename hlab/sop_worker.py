"""Inspect or run a numeric experiment in an isolated Houdini process."""
import hashlib
import json
import math
import sys
from pathlib import Path

import hou
import numpy as np


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


def work(req,folder):
    hou.hipFile.load(req["hip"],suppress_save_prompt=True)
    if req["action"] == "mechanical_rig":
        from rig_worker import build
        return build(req)
    if req["action"] == "mechanism":
        from mechanism_worker import build
        return build(req)
    if req["action"] == "animation_gap":
        from animation_gap import measure_frames
        return measure_frames(req)
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


if __name__=="__main__":
    folder=Path(sys.argv[1])
    try:
        result={"ok":work(json.loads((folder/"request.json").read_text(encoding="utf8")),folder)}
    except Exception as exc:
        result={"error":f"{type(exc).__name__}: {exc}"}
        if hasattr(exc, "gap_hint"):
            result["gap_hint"] = exc.gap_hint
    (folder/"reply.json").write_text(json.dumps(result,allow_nan=False),encoding="utf8")
