import functools
import json

from typing import Literal

import anyio

from mcp.server.fastmcp import Image
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from . import cancel
from .bridge import call
from .graph_schema import Edit
from .catalog import ResearchMCP
from .media import png, sheet, viewport_image
from .improvements import GapReport, Proposal
from .mechanical_rig import Joint
from .mechanisms import FourBar, Reeving, Transfer
from .storage import details, home, ident, record, search, sha, uid
from .wfc_api import Cell, Sockets, Tile

mcp = ResearchMCP("Houdini Research", instructions=(
    "Start with window_session or knowledge. Discover specialist operations via domain_recipe(action='catalog'). "
    "Use the dedicated research window for live edits. For an unsupported operation, a manual workaround, or an unexplained "
    "mismatch, inspect the relevant tools and evidence. Report a reproducible limitation using improvement, "
    "reuse any gap ID already returned, and propose the smallest change with a pass/fail retest. "
    "A correctly rejected scene is feedback on the scene. Show proposals to the user."))


def tool(*args, **kwargs):
    """mcp.tool for a blocking body. The body runs in a worker thread, so the server keeps answering other calls
    while Houdini cooks or renders. Cancelling the call, or closing the connection, raises the flag its waiting loops
    watch (hlab.cancel), which ends the Houdini worker and the renderers it started. The plain function is returned,
    so tools can still call each other directly."""
    register = mcp.tool(*args, **kwargs)

    def decorate(body):
        @functools.wraps(body)
        async def threaded(*call_args, **call_kwargs):
            flag = cancel.new_flag()
            try:
                return await anyio.to_thread.run_sync(
                    functools.partial(cancel.run, flag, body, *call_args, **call_kwargs), abandon_on_cancel=True)
            except anyio.get_cancelled_exc_class():
                flag.set()
                raise

        register(threaded)
        return body

    return decorate


def illustrated(data, im):
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False)), Image(data=png(im),format="png").to_image_content()]


def selected_directory(session_id):
    if not session_id:
        return home()
    from .window import registered

    for directory, session in registered(home()):
        if session["id"] == session_id:
            return directory
    raise ValueError("Select a live window_session ID")


def live_call(operation, session_id, **args):
    from .bridge import call_in

    return call_in(selected_directory(session_id), operation, expected_session=session_id or None, **args)


READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


@tool(annotations=READ)
def node_types(category: str = "Sop", query: str = "", offset: int = 0, limit: int = 20, session_id: str = "") -> dict:
    """Discover installed Houdini types by category, query and page before creating nodes."""
    return live_call("graph_types", session_id, category=category, query=query, offset=offset, limit=limit)


@tool(annotations=READ)
def graph_read(path: str = "/obj", depth: int = 1, offset: int = 0, limit: int = 20,
               snapshot: bool = False, session_id: str = "") -> dict:
    """Page a live network's nodes, wires, flags, diagnostics and nondefault parameters. Snapshot optionally records a diff baseline."""
    return live_call("graph_read", session_id, path=path, depth=depth, offset=offset, limit=limit, snapshot=snapshot)


@tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
def graph_edit(ops: list[Edit], label: str = "graph_edit", allow_delete: list[str] | None = None,
               require_clean: bool = True, session_id: str = "") -> dict:
    """Atomically create, wire, set, flag, rename or delete live OPs. Provide absolute paths and optionally expected
    old values; failures roll back. One successful batch is one undo. Code-bearing writes require host opt-in.
    Built-in types run Houdini's creation scripts, so a cam has resx, focal and projection and a geo its vm_ render
    parameters; each create step reports init_scripts. A set step returns the value, or for text over 200
    characters a preview, length and sha256 of the stored text."""
    return live_call("graph_edit", session_id, ops=[op.model_dump(exclude_unset=True) for op in ops],
                     label=label, allow_delete=allow_delete or [], require_clean=require_clean)


@tool(annotations=READ)
def cook(node: str, frame: int | None = None, session_id: str = "") -> dict:
    """Cook a live SOP and return measured geometry, attributes, bounds, errors and warnings."""
    return live_call("graph_cook", session_id, node=node, frame=frame)


@tool(annotations=READ, structured_output=False)
def capture(frame: int, camera: str = "", session_id: str = ""):
    """Capture a live Scene Viewer PNG, optionally through a camera OBJ. Restore the original time and view."""
    from .bridge import call_in

    directory = selected_directory(session_id)
    sample = call_in(directory, "graph_capture", expected_session=session_id or None, frame=frame, camera=camera)
    return illustrated(sample, viewport_image(sample, directory))


@tool(annotations=READ)
def diff(key: str, path: str = "", session_id: str = "") -> dict:
    """Compare the live graph at path to a saved graph snapshot or a trusted recipe ID."""
    return live_call("graph_diff", session_id, key=key, path=path)


@mcp.tool(structured_output=False)
async def domain_recipe(action: Literal["catalog", "run"] = "catalog", domain: str = "", name: str = "",
                        arguments: dict | None = None) -> CallToolResult:
    """Browse domain names, then descriptions by domain or the original input schema by name. Use run with
    a listed name and its arguments for the chosen domain."""
    return await mcp.domain_recipe(action, domain, name, arguments)


@tool()
def window_session(action: Literal["list", "state", "open", "save"] = "list", session_id: str = "",
                   hip: str = "") -> dict:
    """List managed Houdini windows; state/open/save target a returned session_id (the window's id).
    Open a saved HIP in that existing GUI. Unsaved work is retained and reported. save writes the live
    scene to its own HIP, or to hip, a new absolute .hip path (never over another file), and returns
    its bytes and sha256, so karma and saved node_lab studies can read what graph_edit built."""
    from .window import manage
    return manage(home(), action, session_id, hip)


@tool()
def session(initialize: bool = False) -> dict:
    """Read live controls, geometry and version; initialize creates a fixture in an empty research window."""
    return call("initialize" if initialize else "state")


@tool()
def adjust(changes: dict[str, float] | None = None, preset: str = "") -> dict:
    """Apply only named controls to the live fixture; A/B/C optionally loads a fireworks starting point."""
    return call("set_controls", changes=changes or {}, preset=preset)


@tool(structured_output=False)
def observe(frame: int = 36):
    """Read a real live viewport PNG and its measurements, then restore the previous frame."""
    sample = call("capture",frame=frame)
    return illustrated(sample, viewport_image(sample))


@tool(structured_output=False)
def experiment(control: str, samples: list[float], frame: int = 36):
    """Sweep one supported control, capture evidence and restore baseline. Returns a small comparison sheet."""
    card = call("sweep",control=control,samples=samples,frame=frame)
    points = details(card["id"])["details"]["samples"]
    rows = [[(f"{control} = {p['actual']:g}   F{p['frame']}",p) for p in points[i:i+3]] for i in range(0,len(points),3)]
    return illustrated(card,sheet(rows))


@tool(structured_output=False)
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


@tool(structured_output=False)
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


@tool()
def recipe(action: str, title: str = "", reason: str = "", key: str = "", origin: str = "baseline") -> dict:
    """save live graph, origin baseline/test/user_selected (only on actual human selection); replay verified graph by ID."""
    if action == "save" and title.strip():
        if origin not in {"baseline","test","user_selected"}:
            raise ValueError("Unknown recipe origin")
        return call("checkpoint",title=title[:120],reason=reason[:600],parent=key or None,origin=origin)
    if action == "replay":
        from .sop_lab import verify_recipe
        key = ident(key)
        return call("replay",key=key,fresh_check=verify_recipe(key))
    raise ValueError("Use save with a title, or replay with a recipe key")


@tool()
def knowledge(topic: str = "", kind: str = "", key: str = "", limit: int = 6, offset: int = 0,
              status: str = "", query: str = "", session_id: str = "") -> dict:
    """Search short cards by topic/kind, or expand one record by ID. Raw images stay on disk."""
    if session_id:
        return live_call("graph_knowledge", session_id, key=key, topic=topic, kind=kind,
                         limit=limit, offset=offset, status=status, query=query)
    return details(key) if key else search(topic,kind,limit,offset,status,query)


@tool(structured_output=False)
def evidence(key: str, variant: str = "", index: int = 0, session_id: str = ""):
    """Return one checksum-verified image from an experiment, a motion study, or a named comparison variant."""
    row = knowledge(key=key,session_id=session_id)
    data = row["details"]
    if row["kind"]=="comparison" and variant in data["candidates"]:
        samples = data["candidates"][variant]["samples"]
    elif row["kind"] in ("experiment","motion","render") and not variant:
        samples = data["samples"]
    else:
        raise ValueError("Choose an experiment or motion ID, or pass a comparison ID and one of its variant names")
    if not 0 <= index < len(samples):
        raise ValueError("Image index outside the recorded range")
    sample = samples[index]
    if "image_id" not in sample:
        raise ValueError("This run recorded geometry only. Use knowledge(key) for its measured results.")
    directory = selected_directory(session_id) if session_id else None
    return illustrated({"id": key, "variant": variant, **sample}, viewport_image(sample, directory))


@tool()
def improvement(request: GapReport | Proposal) -> dict:
    """Report an observed gap or workaround with expected/observed behaviour and reproduction. Reuse a stable
    capability key after searching knowledge. Propose a minimal improvement and pass/fail retest for a gap ID.
    Proposals are local, searchable drafts. A proposal alone cannot resolve a gap."""
    from .improvements import propose, report
    return report(request) if isinstance(request, GapReport) else propose(request)


@tool()
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
            # Earlier node_lab evidence used one new hython per SOP experiment. GUI runs had no such isolation.
            process = run.get("process", "fresh" if "request" in run and "repeat_signature" in run else "live")
            if process != "fresh" or card["status"] in {"conflict", "conditions_changed"}:
                continue
            base = run["baseline"]
            if "repeat_signature" in run:
                signatures.append(json.dumps(run.get("series_signature",run["repeat_signature"]),sort_keys=True))
            else:
                signatures.append((base["version"], base["node_type"], run["control"],
                    json.dumps(base["parameters"], sort_keys=True), base["metrics"]["scatter_sha256"],
                    tuple((s["actual"],s["frame"],s["metrics"]["output_sha256"]) for s in run["samples"])))
        if len(signatures)<2 or len(set(signatures))!=1:
            raise ValueError("Link two fresh runs of the same control, baseline, samples and results. Replay twice if the original sweep was warm.")
    if kind=="gap" and status=="resolved":
        opened = [c for c in cards if c["kind"] == "gap" and c["status"] == "open"]
        original_evidence = {key for c in opened for key in c["details"].get("sources", [])}
        unresolved = {c["details"]["capability"] for c in opened if "capability" in c["details"]}
        has_retest = any(c["id"] not in original_evidence and
                         c["details"].get("gap_capability") not in unresolved and
                         c["kind"] not in {"gap", "preference", "gap_observation", "improvement"} for c in cards)
        if not opened or not has_retest:
            raise ValueError("Link the original open gap and separate retest evidence. A proposal is not a retest.")
    return record(kind,title[:120],[tag.strip().lower()[:48] for tag in topics],summary[:700],
                  {"sources":[c["id"] for c in cards]},status=status)


def main():
    mcp.run()


@tool(structured_output=False)
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


@tool(structured_output=False)
def node_lab(action: str = "inspect", hip: str = "", node: str = "/obj/RAIN/Wave_1",
             control: str = "", values: list[float] | None = None, frame: int = 38,
             renderer: str = "", topic: str = "", query: str = "", offset: int = 0,
             limit: int = 8, key: str = "", changes: dict[str,float] | None = None,
             witness: str = "", note: str = "", prediction: str = "", expect_change: bool | None = None,
             scope: Literal["saved","live"] = "saved", variants: dict[str,dict[str,float]] | None = None,
             frames: list[int] | None = None, capture: bool = False, camera: str = "", session_id: str = ""):
    """Study saved HIPs or live SOPs. Live sweep, compare (named variants), motion (frames) restore all controls;
    optional witness SOP and capture. Saved compare/motion optionally render with a Mantra ROP. Saved
    inspect/nodes, sweep/replay, variant/restore and frame remain available."""
    if scope == "live" or action in ("compare","motion"):
        args = dict(action=action,node=node,control=control,values=values,frame=frame,witness=witness,
                    variants=variants,frames=frames,capture=capture,camera=camera,topic=topic,
                    prediction=prediction,expect_change=expect_change,changes=changes)
        if scope=="live":
            if action not in ("sweep","compare","motion") or hip or renderer or key:
                raise ValueError("For live SOPs use sweep, compare or motion; use graph_read for inspection")
            result=live_call("live_study",session_id,**args)
        else:
            from .sop_lab import study_saved
            result=study_saved(hip,renderer=renderer,**args)
        return [TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]
    from .sop_lab import run,variant,render_frame
    if action=="frame":
        data=render_frame(hip,frame,renderer or "/out/RAIN_BEAUTY",key)
        return illustrated(data,viewport_image(data))
    if action in ("variant","restore"):
        result=variant(action,hip,node,changes or {},witness,frame,topic,note,key)
    else:
        result=run(action,hip,node,control,values or [],frame,renderer,topic,query,offset,limit,key,prediction,expect_change)
    return [TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]


@tool()
def mechanical_rig(hip: str, joints: list[Joint], frame: int = 1, output: str = "",
                   replace_motion: bool = False) -> dict:
    """Build a parent-first tree of native fixed, hinge and slider OBJ joints on existing unparented geometry OBJs.
    Each edge connects siblings. World-space pivots and axes refer to the bind pose. Drives start at zero on that frame.
    Saves a new sibling HIP, reopens and verifies parentage and rest poses. replace_motion explicitly freezes the selected objects'
    existing animated transform channels at the bind pose before applying new joint keys. Read returned control paths to edit drive."""
    from .mechanical_rig import run
    return run(hip, joints, frame, output, replace_motion)


@tool(annotations=READ)
def wfc_layout(columns: int, rows: int, tiles: list[Tile], seed: int = 0,
               cells: list[Cell] | None = None, edges: Sockets | None = None,
               connected_socket: str | None = None, loop_free: bool = False) -> dict:
    """Solve a 2D module layout with 1-256 cells and 1-64 tiles using weighted entropy and socket propagation.
    Rows are bottom-up, x/y zero-based. Adjacent sockets must match; a one-tile cell allow-list locks it.
    Optional edges constrain all four boundaries. connected_socket makes every cell reachable via that socket;
    loop_free also requires a tree. Returns seed, tile-name layout and search statistics, or an explicit failure.
    The same ordered rules, seed and solver version reproduce a layout. Geometry is built by the caller."""
    from .wfc import solve
    return solve(columns, rows, [t.model_dump() for t in tiles], seed,
                 [c.model_dump() for c in cells or []], edges.model_dump() if edges else None,
                 connected_socket, loop_free)


@tool()
def mechanism(hip: str, spec: FourBar | Reeving | Transfer, output: str = "", topic: str = "") -> dict:
    """Build live constraints in a new sibling HIP. fourbar: planar XY linkage with optional rigid part bindings.
    reeving: constant-radius 2/4-fall rope with a drum drive, optionally linked to model channels.
    transfer: switch a payload between sibling supports at seated local anchors without a world-space jump.
    Optional topic saves searchable verification evidence."""
    from .mechanisms import run
    return run(hip, spec, output, topic)


@tool()
def animation_gap(hip: str, upper: str, lower: str, start: int, end: int,
                  axis: str = "y", minimum: float | None = None, maximum: float | None = None,
                  topic: str = "") -> dict:
    """Check a saved HIP's signed world-axis bounds gap (upper min minus lower max) at every integer frame, inclusive.
    Pass two geometry OBJ or SOP paths and optional limits in scene units. Returns extrema, first violation and missing frames.
    Measures projected bounds, not mesh contact. Supply topic to save a searchable evidence record."""
    from .animation_gap import run
    return run(hip, upper, lower, start, end, axis, minimum, maximum, topic)


@tool(structured_output=False)
def karma(action: Literal["presets", "inspect", "render", "compare", "animate", "save_preset"] = "presets",
          hip: str = "", camera: str = "", frame: int | None = None, frames: list[int] | None = None, fps: int = 24,
          preset: str = "preview", changes: dict[str, bool | int | float | str] | None = None,
          variants: dict[str, dict[str, bool | int | float | str | dict[str, bool | int | float | str] | list[str]]] | None = None,
          zoom: list[float] | None = None, rop: str = "", topic: str = "", name: str = "", note: str = "",
          overrides: dict[str, bool | int | float | str] | None = None, hide: list[str] | None = None):
    """Test renders of a saved HIP (path, sample:..., rain, afterglow or karma-probe) with Karma XPU/CPU or, where it is
    installed, Chaos Vantage (changes.engine = vantage: exported to USD, about 1 s a frame plus 10-25 s to start); the
    HIP is never saved. presets lists named settings and adjustable controls. inspect lists cameras, lights, ROPs,
    material support, the materials each engine converts (legacy /shop shaders, and Principled with bump,
    transparency or cut-out maps on XPU, become MaterialX in memory: convert_materials) and materials with unreal PBR values.
    changes.lighting swaps the scene's lights for a day, overcast, night or product studio look placed relative to
    the camera (light_angle, light_elevation, light_exposure, light_fill, keep_scene_lights), or for an HDRI panorama
    (lighting = hdri with hdri = its path; light_angle turns its sun). For photoreal results,
    round_edges (millimetres) rounds hard edges and pbr_fix corrects unreal material values, on the render copy only.
    render returns one image limited in size and time, with effective settings, conversions, lighting, seconds and
    GPU evidence; topic saves it as evidence. compare renders 2-4 variants ({name: {preset?, controls}}) on one camera
    and frame, optionally zoomed to [left, top, right, bottom] fractions, and saves a comparison. animate renders
    frames=[first, last] to numbered PNGs and an MP4 at fps (Vantage up to 480 frames in one run; Karma up to 240, in
    husk runs of 48 frames that each load the scene once). overrides sets scene parameters for this render only
    ({"/obj/node/parm": value}; animation on them is replaced; code-capable parameters need the host opt-in) and hide
    lists objects to leave out; in compare a variant may carry its own overrides and hide. save_preset names a base
    preset plus changes for later use."""
    from . import karma as studio
    if action == "presets":
        result = studio.presets()
    elif action == "save_preset":
        result = studio.save_preset(name, preset, changes, note)
    elif action == "inspect":
        result = studio.inspect(hip)
    elif action == "render":
        return illustrated(*studio.render(hip, camera, frame, preset, changes, rop, topic, note, overrides, hide))
    elif action == "animate":
        return illustrated(*studio.animate(hip, camera, frames, preset, changes, fps, rop, topic, note, overrides, hide))
    else:
        return illustrated(*studio.compare(hip, variants, camera, frame, rop, topic, zoom, note, overrides, hide))
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


@mcp.tool()
async def fx_watch(action: str = "status", job: str = "", manifest: str = "", query: str = "",
                   offset: int = 0, limit: int = 12, cursor: str = "", seconds: int = 20) -> dict:
    """Register a local Houdini job manifest, read real solve/XPU progress, wait for a change (up to 45 s), or page constraint failure events by part. Never submits a render."""
    from .fx_watch import inspect
    return await inspect(action,job,manifest,query,offset,limit,cursor,seconds)


if __name__ == "__main__":
    main()
