import json

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import TextContent

from .bridge import call
from .media import png, sheet, viewport_image
from .storage import details, home, ident, record, search, sha, uid

mcp = FastMCP("Houdini Research", instructions="Start with session or knowledge. Execute scene operations in the dedicated research window. Evidence is opt-in.")


def illustrated(data, im):
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False)), Image(data=png(im),format="png").to_image_content()]


@mcp.tool()
def session(initialize: bool = False) -> dict:
    """Read live controls, geometry and version; initialize creates a fixture in an empty research window."""
    return call("initialize" if initialize else "state")


@mcp.tool()
def adjust(changes: dict[str, float] | None = None, preset: str = "") -> dict:
    """Apply only named controls to the live fixture; A/B/C optionally loads a fireworks starting point."""
    return call("set_controls", changes=changes or {}, preset=preset)


@mcp.tool(structured_output=False)
def observe(frame: int = 36):
    """Read a real live viewport PNG and frame measurements. Positions the research window on that frame."""
    sample = call("capture",frame=frame)
    return illustrated(sample, viewport_image(sample))


@mcp.tool(structured_output=False)
def experiment(control: str, samples: list[float], frame: int = 36):
    """Sweep one supported control, capture evidence and restore baseline. Returns a small comparison sheet."""
    card = call("sweep",control=control,samples=samples,frame=frame)
    points = details(card["id"])["details"]["samples"]
    rows = [[(f"{control} = {p['actual']:g}   F{p['frame']}",p) for p in points[i:i+3]] for i in range(0,len(points),3)]
    return illustrated(card,sheet(rows))


@mcp.tool(structured_output=False)
def compare(frames: list[int] | None = None):
    """Compare A/B/C on identical frames and restore active controls. Returns a contact sheet and a comparison ID."""
    frames = [23,36,47] if frames is None else frames
    card = call("compare",frames=frames)
    runs = details(card["id"])["details"]["candidates"]
    rows = [[(f"{key}   F{sample['frame']}",sample) for sample in item["samples"]] for key,item in runs.items()]
    im = sheet(rows)
    output = home() / "records" / card["id"] / "comparison.png"
    im.save(output)
    return illustrated({**card,"sheet":str(output)},im)


@mcp.tool(structured_output=False)
def motion(start: int = 12, end: int = 53):
    """Capture consecutive real frames for the active look. Returns a local animated GIF and representative frames."""
    info = call("motion",start=start,end=end)
    frames = info["samples"]
    images = [viewport_image(sample) for sample in frames]
    folder = home() / "clips"
    folder.mkdir(exist_ok=True,parents=True)
    path = folder / (uid()+".gif")
    # Cumulative rounded frame times keep playback close to the scene FPS at GIF precision.
    fps = info["fps"]
    durations = [10*(round((i+1)*100/fps)-round(i*100/fps)) for i in range(len(images))]
    images[0].save(path,save_all=True,append_images=images[1:],duration=durations,loop=0,disposal=2)
    row = [(f"F{frames[i]['frame']}",frames[i]) for i in (0,len(frames)//2,len(frames)-1)]
    return illustrated({"path":str(path),"sha256":sha(path),"frames":len(frames),"fps":fps,"start":start,"end":end},sheet([row]))


@mcp.tool()
def recipe(action: str, title: str = "", reason: str = "", key: str = "", origin: str = "baseline") -> dict:
    """save live graph, origin baseline/test/user_selected (only on actual human selection); replay verified graph by ID."""
    if action == "save" and title.strip():
        if origin not in {"baseline","test","user_selected"}:
            raise ValueError("Unknown recipe origin")
        return call("checkpoint",title=title[:120],reason=reason[:600],parent=key or None,origin=origin)
    if action == "replay":
        return call("replay",key=ident(key))
    raise ValueError("Use save with a title, or replay with a recipe key")


@mcp.tool()
def knowledge(topic: str = "", kind: str = "", key: str = "", limit: int = 6, offset: int = 0,
              status: str = "", query: str = "") -> dict:
    """Search short cards by topic/kind, or expand one record by ID. Raw images stay on disk."""
    return details(key) if key else search(topic,kind,limit,offset,status,query)


@mcp.tool(structured_output=False)
def evidence(key: str, variant: str = "", index: int = 0):
    """Return one archived, checksum-verified viewport image from an experiment or A/B/C comparison."""
    row = details(key)
    data = row["details"]
    if row["kind"]=="comparison" and variant in data["candidates"]:
        samples = data["candidates"][variant]["samples"]
    elif row["kind"]=="experiment" and not variant:
        samples = data["samples"]
    else:
        raise ValueError("Use an experiment ID, or a comparison ID plus variant A/B/C")
    if not 0 <= index < len(samples):
        raise ValueError("Image index outside the recorded range")
    sample = samples[index]
    if "image_id" not in sample:
        raise ValueError("This run recorded geometry only. Use knowledge(key) for its measured results.")
    return illustrated({"id":key,"variant":variant,**sample},viewport_image(sample))


@mcp.tool()
def learn(kind: str, title: str, summary: str, topics: list[str], sources: list[str],
          status: str = "observed") -> dict:
    """Attach a gap, project preference, node résumé or reuse outcome to existing evidence; preserve earlier records."""
    allowed = {"gap":{"open","resolved"}, "preference":{"project"}, "node":{"observed","reproduced","conflict"},
               "reuse":{"reproduced","conflict","conditions_changed"}}
    if status not in allowed.get(kind,set()) or not title.strip() or not summary.strip():
        raise ValueError("Provide an allowed kind/status, title and summary")
    if not 1 <= len(topics) <= 8 or len(sources)>12 or (kind!="gap" and not sources):
        raise ValueError("Provide tags and relevant evidence IDs")
    cards = [details(key) for key in dict.fromkeys(sources)]
    if kind=="node" and not any(c["kind"]=="experiment" for c in cards):
        raise ValueError("A node résumé requires an experiment")
    if kind=="node" and status=="reproduced":
        signatures = []
        for card in cards:
            if card["kind"] != "experiment":
                continue
            run = card["details"]
            base = run["baseline"]
            if "repeat_signature" in run:
                signatures.append(json.dumps(run.get("series_signature",run["repeat_signature"]),sort_keys=True))
            else:
                signatures.append((base["version"], base["node_type"], run["control"],
                    json.dumps(base["parameters"], sort_keys=True), base["metrics"]["scatter_sha256"],
                    tuple((s["actual"],s["frame"],s["metrics"]["output_sha256"]) for s in run["samples"])))
        if len(signatures)<2 or len(set(signatures))!=1:
            raise ValueError("Link repeated runs of the same control, baseline, samples and results")
    if kind=="gap" and status=="resolved" and (not any(c["kind"]=="gap" for c in cards) or len(cards)<2):
        raise ValueError("Link the original gap and the evidence that resolved it")
    return record(kind,title[:120],[tag.strip().lower()[:48] for tag in topics],summary[:700],
                  {"sources":[c["id"] for c in cards]},status=status)


def main():
    mcp.run()


@mcp.tool(structured_output=False)
def afterglow(action: str = "state", key: str = "", changes: dict[str,float] | None = None,
              smoke_from: str = "", flash_from: str = "", note: str = "", frame: int = 53,
              start: int = 47, end: int = 62):
    """Residual smoke shot: state reads live knobs; revise saves a candidate with optional smoke_from or flash_from; frame or clip renders in Mantra. Controls: smoke density scale, flash gain, duration in frames."""
    from . import afterglow as shot
    if action=="state":
        result={"live":shot.live(),"current":shot.current(),"bounds":shot.LIMITS}
    elif action=="revise":
        result=shot.revise(changes or {},note,key,smoke_from,flash_from)
    elif action in ("frame","clip"):
        info,im=shot.take(key,frame,frame) if action=="frame" else shot.take(key,start,end,draft=True)
        return illustrated(info,im)
    else:
        raise ValueError("Use state, revise, frame or clip")
    return [TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]


@mcp.tool(structured_output=False)
def node_lab(action: str = "inspect", hip: str = "", node: str = "/obj/RAIN/Wave_1",
             control: str = "", values: list[float] | None = None, frame: int = 38,
             renderer: str = "", topic: str = "", query: str = "", offset: int = 0,
             limit: int = 8, key: str = "", changes: dict[str,float] | None = None,
             witness: str = "", note: str = "", prediction: str = "", expect_change: bool | None = None):
    """Inspect/nodes: paged discovery. Sweep a numeric SOP control with a prediction and optional Mantra images. Replay repeats an experiment; variant forks a scene_recipe; restore validates it; frame renders it."""
    from .sop_lab import run,variant,render_frame
    if action=="frame":
        data=render_frame(hip,frame,renderer or "/out/RAIN_BEAUTY",key)
        return illustrated(data,viewport_image(data))
    if action in ("variant","restore"):
        result=variant(action,hip,node,changes or {},witness,frame,topic,note,key)
    else:
        result=run(action,hip,node,control,values or [],frame,renderer,topic,query,offset,limit,key,prediction,expect_change)
    return [TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]


@mcp.tool()
async def fx_watch(action: str = "status", job: str = "", manifest: str = "", query: str = "",
                   offset: int = 0, limit: int = 12, cursor: str = "", seconds: int = 20) -> dict:
    """Register a local Houdini job manifest, read real solve/XPU progress, wait for a change (up to 45 s), or page constraint failure events by part. Never submits a render."""
    from .fx_watch import inspect
    return await inspect(action,job,manifest,query,offset,limit,cursor,seconds)


if __name__ == "__main__":
    main()
