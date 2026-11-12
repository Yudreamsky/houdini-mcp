"""Karma and Chaos Vantage test renders of saved HIPs: named presets, bounded size and time, searchable evidence."""
import math
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import vantage
from .karma_spec import LIGHTING, PRESETS, checked, controls, lighting, look_settings, settings
from .storage import created_now, home, read, record, sha, uid, write

SAMPLE = "karma-probe"
ENGINES = {"xpu": "XPU", "cpu": "CPU", "vantage": "Vantage"}
# Frames one animate call renders. Vantage renders the range in one run. Karma renders it in runs of up to CHUNK
# frames: each run loads the HIP and starts husk once, and a run that fails costs at most that many frames.
MAX_FRAMES = {"vantage": 480, "karma": 240}
CHUNK = 48
RETRY_PAUSE = 30.  # seconds before continuing after a run stopped early; a display driver that reset needs a moment


def preset_file():
    return home() / "karma" / "presets.json"


def saved_presets():
    path = preset_file()
    return read(path) if path.is_file() else {}


def presets():
    saved = saved_presets()
    return {"builtin": [{"name": k, "label": p["label"], "note": p["note"], "settings": p["settings"]}
                        for k, p in PRESETS.items()],
            "saved": [{"name": k, "base": v["base"], "changes": v["changes"], "note": v["note"],
                       "settings": settings(k, None, saved)} for k, v in saved.items()],
            "lighting": [{"name": k, **v} for k, v in LIGHTING.items()],
            "controls": controls()}


def save_preset(name, preset, changes, note=""):
    name = name.strip()
    if not 1 <= len(name) <= 40 or name in PRESETS:
        raise ValueError("Name the preset with 1–40 characters, different from the built-in presets")
    if preset not in PRESETS:
        raise ValueError(f"Base a saved preset on one of: {', '.join(PRESETS)}")
    changes = checked(changes)
    if not changes:
        raise ValueError("A saved preset needs at least one change")
    saved = saved_presets()
    replaced = name in saved
    saved[name] = {"base": preset, "changes": changes, "note": note.strip()[:300], "saved_at": created_now()}
    write(preset_file(), saved)
    return {"name": name, "replaced": replaced, "base": preset, "changes": changes,
            "settings": settings(name, None, saved)}


def scene(hip):
    from .sop_lab import hip_path, worker
    if not hip:
        raise ValueError(f"Choose a saved HIP: an absolute path, sample:..., rain, afterglow or {SAMPLE}")
    if hip != SAMPLE:
        return hip_path(hip)
    path = home() / "shots" / SAMPLE / "Karma-probe.hip"
    if not path.is_file():
        with job_folder("houdini-karma-sample-") as job:
            worker({"action": "karma_sample", "target": str(path)}, job)
    return path


@contextmanager
def job_folder(prefix):
    # A failed cleanup must not replace the render's own error.
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as folder:
        yield Path(folder)


def inspect(hip):
    from .sop_lab import worker
    path = scene(hip)
    with job_folder("houdini-karma-inspect-") as job:
        return {"hip": str(path), **worker({"action": "karma_inspect", "hip": str(path)}, job)}


def base_of(preset, saved):
    return preset if preset in PRESETS else saved.get(preset, {}).get("base", preset)


def gpu_load():
    """NVIDIA utilisation and free memory when nvidia-smi is available, else None."""
    try:
        line = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True,
                              timeout=10, check=True).stdout.splitlines()[0]
        busy, used, total = (float(v) for v in line.split(","))
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
    return {"utilization_percent": busy, "free_mib": total - used}


def load_notes(load, engine="xpu"):
    """Warn when other programs hold the GPU before an XPU or Vantage render."""
    if not load:
        return []
    rows = []
    if load["utilization_percent"] >= 70:
        rows.append(f"开始渲染时显卡使用率已有 {load['utilization_percent']:g}%（其他程序在用，例如本地 AI 模型），"
                    + ("XPU 可能变慢或到时间上限；急用时可改 engine=cpu。" if engine == "xpu"
                       else "Vantage 可能变慢，显存不够时会启动失败。"))
    if load["free_mib"] < 4096:
        rows.append(f"显存只剩约 {load['free_mib'] / 1024:.1f} GB，较大的场景可能放不下。")
    return rows


def progress_note(run):
    share = run.get("progress_percent")
    if run["status"] != "time_limit" or share is None:
        return []
    text = f"到时间上限时只完成了约 {share:g}%"
    if run["settings"]["engine"] == "xpu" and share < 50:
        return [text + "。XPU 第一次遇到新材质要编译着色器，或显卡被其他程序占用时会这样；再渲一次通常会快，也可加大 time_limit。"]
    return [text + "；可加大 time_limit 或降低分辨率。"]


def keep(picture, log_file):
    """Copy a rendered image and its log into the evidence store."""
    image_id = uid()
    target = home() / "images" / (image_id + ".png")
    log = home() / "karma" / "logs" / (image_id + ".log")
    for folder in (target.parent, log.parent):
        folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(picture, target)
    shutil.copyfile(log_file, log)
    return {"image_id": image_id, "sha256": sha(target), "path": str(target), "log": str(log)}


def run_one(path, chosen, camera, frame, rop, base=""):
    if chosen.get("engine") == "vantage":
        return run_vantage(path, chosen, camera, frame)
    from .sop_lab import worker
    load = gpu_load() if chosen.get("engine", "xpu") == "xpu" else None
    with job_folder("houdini-karma-") as job:
        info = worker({"action": "karma_render", "hip": str(path), "camera": camera, "frame": frame,
                       "rop": rop, "preset": base, "settings": chosen}, job)
        if info["settings"]["engine"] == "xpu":
            info.update(gpu_load=load, notes=load_notes(load) + info["notes"])
        info["notes"] = progress_note(info) + info["notes"]
        stored = keep(job / info.pop("file"), job / info.pop("log"))
    return {**info, **stored}


def vantage_result(info, chosen, text, tries, seconds, load):
    """A Vantage render described like a Karma one, so summaries, captions and comparisons read alike."""
    found = vantage.read_log(text)
    rows = load_notes(load, "vantage") + info["notes"]
    if tries > 1:
        rows.append(f"Vantage 启动时崩溃了 {tries - 1} 次（3.3 版偶尔这样），自动重启后成功。")
    if found.get("log_errors"):
        rows.append("Vantage 日志里有报错：" + "；".join(found["log_errors"][:2]))
    used = {"engine": "vantage", "samples": chosen.get("samples", 64),
            "denoiser": "off" if chosen.get("denoiser") == "off" else "on", "motion_blur": bool(chosen.get("motion_blur")),
            "round_edges": chosen.get("round_edges", 0.), "pbr_fix": bool(chosen.get("pbr_fix")),
            **look_settings(lighting(chosen))}
    return {**found, "frame": info["frames"][0], "camera": info["camera"], "rop": "", "temporary_rop": False,
            "resolution": info["resolution"], "settings": used, "status": "completed",
            "seconds": round(info["export_seconds"] + seconds, 2), "export_seconds": info["export_seconds"],
            "vantage_seconds": round(seconds, 2), "vantage_tries": tries, "gpu_verified": "gpu" in found,
            "gpu_load": load, "lights": info["lights"], "materials": info["materials"], "lighting": info["lighting"],
            "photoreal": info["photoreal"], "normals_added": info["normals_added"], "usd_edits": info["usd_edits"],
            "notes": rows}


def export_vantage(path, chosen, camera, frames, job):
    from .sop_lab import worker
    vantage.executable()  # fail before the export when Vantage is not installed
    return worker({"action": "vantage_export", "hip": str(path), "camera": camera, "frames": frames,
                   "settings": chosen}, job)


def run_vantage(path, chosen, camera, frame):
    """Export the HIP to USD in the worker, then render it with Chaos Vantage on this machine."""
    load = gpu_load()
    with job_folder("houdini-vantage-") as job:
        info = export_vantage(path, chosen, camera, None if frame is None else [frame, frame], job)
        started = time.perf_counter()
        pictures, text, tries = vantage.run(job, info, chosen)
        seconds = time.perf_counter() - started
        stored = keep(pictures[0], job / "vantage.log")
    return {**vantage_result(info, chosen, text, tries, seconds, load), **stored}


def sample(run):
    keys = ("image_id", "sha256", "frame", "camera", "resolution", "seconds", "status", "settings", "gpu_verified")
    return {k: run[k] for k in keys}


def summary(run):
    s = run["settings"]
    engine = s.get("engine") or "scene"
    text = (f"{ENGINES.get(engine, engine)} {run['resolution'][0]}×{run['resolution'][1]}，{s['samples']} 采样，"
            f"降噪 {s['denoiser']}，用时 {run['seconds']:g} 秒")
    if engine == "vantage":
        text += vantage.summary_seconds(run)
    elif engine == "xpu":
        share = sum(d["contribution_percent"] for d in run["devices"] if d["type"].lower() == "optix")
        text += f"，显卡贡献 {share:g}%"
    if run.get("materials") and run["materials"]["converted"]:
        text += f"，临时转换材质 {len(run['materials']['converted'])} 个"
    if s.get("round_edges"):
        text += f"，圆角 {s['round_edges']:g} 毫米"
    if (run.get("photoreal") or {}).get("pbr_fixes"):
        text += f"，按真实材料改正 {len(run['photoreal']['pbr_fixes'])} 个材质"
    if s.get("lighting", "scene") != "scene":
        text += f"，灯光{LIGHTING[s['lighting']]['label']}"
        if "light_angle" in s:
            text += f"（方向 {s['light_angle']:g}°，高 {s['light_elevation']:g}°"
            text += f"，补光 {s['light_fill']:+g} 档）" if s.get("light_fill") else "）"
    if run["status"] == "time_limit":
        share = run.get("progress_percent")
        text += f"，到时间上限（约完成 {share:g}%）" if share is not None else "，到时间上限"
    return text


def flatten(path, edge=None, zoom=None):
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
    if zoom:
        w, h = rgba.size
        rgba = rgba.crop((round(zoom[0] * w), round(zoom[1] * h), round(zoom[2] * w), round(zoom[3] * h)))
    canvas = Image.new("RGB", rgba.size, (12, 14, 20))
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    if edge and max(canvas.size) > edge:
        canvas.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return canvas


def render(hip, camera="", frame=None, preset="preview", changes=None, rop="", topic="", note=""):
    saved = saved_presets()
    chosen = settings(preset, changes, saved)
    path = scene(hip)
    before = sha(path)
    run = run_one(path, chosen, camera, frame, rop, base_of(preset, saved))
    run.update(hip=str(path), hip_unchanged=sha(path) == before, preset=preset, summary=summary(run))
    if topic.strip():
        card = record("render", f"Karma {preset} F{run['frame']}"[:120], list(dict.fromkeys([topic.strip().lower(), "render"])),
                      (run["summary"] + ("。" + note.strip() if note.strip() else ""))[:700],
                      {"hip": str(path), "hip_sha256": before, "preset": preset, "request": chosen,
                       "rop": run["rop"], "temporary_rop": run["temporary_rop"], "samples": [sample(run)]})
        run["record"] = card["id"]
    return run, flatten(run["path"], 1280)


def checked_zoom(zoom):
    if zoom is None:
        return None
    if (len(zoom) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in zoom)
            or not 0 <= zoom[0] < zoom[2] <= 1 or not 0 <= zoom[1] < zoom[3] <= 1):
        raise ValueError("zoom is [left, top, right, bottom] as fractions of the image, e.g. [0.4, 0.3, 0.7, 0.6]")
    return [float(v) for v in zoom]


def label_font(size=18):
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def caption(name, run):
    s, (w, h) = run["settings"], run["resolution"]
    seconds = f"{run['seconds']:g} 秒"
    if s.get("engine") == "vantage" and run.get("render_seconds") is not None:
        seconds += f"（渲染 {run['render_seconds']:g}）"
    text = f"{name} · {seconds} · {s['samples']} 采样 · 降噪 {s['denoiser']} · {w}×{h}"
    if s.get("lighting", "scene") != "scene":
        text += f" · {LIGHTING[s['lighting']]['label']}"
    return text + (" · 到时限" if run["status"] == "time_limit" else "")


def contact(runs, zoom=None, width=640):
    return board([(caption(name, run), run["path"]) for name, run in runs.items()], zoom, width)


def board(items, zoom=None, width=640, cols=None):
    """Labelled pictures in a grid: items are (label, path) pairs."""
    font = label_font()
    tiles = []
    for text, path in items:
        im = flatten(path, zoom=zoom)
        scale = width / im.width
        # Enlarged crops keep their real pixels so noise stays visible.
        im = im.resize((width, max(1, round(im.height * scale))),
                       Image.Resampling.NEAREST if scale > 1 else Image.Resampling.LANCZOS)
        tiles.append((text, im))
    cols = cols or (1 if len(tiles) == 1 else 2)
    cell, bar = max(t.height for _, t in tiles), 30
    sheet = Image.new("RGB", (cols * width, math.ceil(len(tiles) / cols) * (cell + bar)), (17, 20, 27))
    draw = ImageDraw.Draw(sheet)
    for i, (text, tile) in enumerate(tiles):
        x, y = (i % cols) * width, (i // cols) * (cell + bar)
        sheet.paste(tile, (x, y + bar))
        draw.text((x + 8, y + 5), text, fill=(237, 226, 199), font=font)
    return sheet


def compare(hip, variants, camera="", frame=None, rop="", topic="", zoom=None, note=""):
    if not variants or not 2 <= len(variants) <= 4:
        raise ValueError('Give 2–4 named variants, e.g. {"A": {"samples": 32}, "B": {"preset": "standard"}}')
    saved = saved_presets()
    plans = {}
    for name, spec in variants.items():
        label = str(name).strip()
        if not 1 <= len(label) <= 24:
            raise ValueError("Variant names must be 1–24 characters")
        spec = dict(spec or {})
        base = spec.pop("preset", "preview")
        plans[label] = (base, settings(base, spec, saved))
    zoom = checked_zoom(zoom)
    path = scene(hip)
    before = sha(path)
    runs = {}
    for name, (base, chosen) in plans.items():
        run = run_one(path, chosen, camera, frame, rop, base_of(base, saved))
        # Later variants use the camera and frame the first one resolved, so every image shows the same shot.
        camera, frame = run["camera"], run["frame"]
        runs[name] = {**run, "preset": base, "summary": summary(run)}
    unchanged = sha(path) == before
    sheet = contact(runs, zoom)
    topics = list(dict.fromkeys([(topic.strip() or "render").lower(), "render"]))
    card = record("comparison", f"Karma 对照 F{frame}：{' / '.join(runs)}"[:120], topics,
                  ("；".join(f"{n}：{r['summary']}" for n, r in runs.items()) + ("。" + note.strip() if note.strip() else ""))[:700],
                  {"hip": str(path), "hip_sha256": before, "camera": camera, "frame": frame, "zoom": zoom,
                   "candidates": {n: {"preset": r["preset"], "request": plans[n][1], "samples": [sample(r)]}
                                  for n, r in runs.items()}})
    output = home() / "records" / card["id"] / "comparison.png"
    sheet.save(output)
    brief = {n: {k: r.get(k) for k in ("preset", "status", "seconds", "resolution", "settings", "gpu_verified",
                                        "materials", "lighting", "notes", "image_id", "path", "summary")} for n, r in runs.items()}
    return {**card, "hip": str(path), "hip_unchanged": unchanged, "camera": camera, "frame": frame,
            "sheet": str(output), "variants": brief}, sheet


def frame_range(frames, engine):
    if (not isinstance(frames, (list, tuple)) or len(frames) != 2 or not all(type(f) is int for f in frames)
            or frames[0] > frames[1]):
        raise ValueError("frames is [first, last] in whole frames, e.g. [1001, 1120]")
    count = frames[1] - frames[0] + 1
    limit = MAX_FRAMES["vantage" if engine == "vantage" else "karma"]
    if count > limit:
        raise ValueError(f"{count} frames is more than one animate call renders with {ENGINES.get(engine, engine)} "
                         f"({limit}); split the range" + ("" if engine == "vantage" else " or use engine vantage"))
    return frames[0], frames[1]


def animate_vantage(path, chosen, camera, first, last, pictures):
    """The whole range in one Vantage run: one USD export and one start-up."""
    load = gpu_load()
    count = last - first + 1
    log = pictures.parent / "vantage.log"
    with job_folder("houdini-vantage-") as job:
        info = export_vantage(path, chosen, camera, [first, last], job)
        started = time.perf_counter()
        frames, text, tries = vantage.run(job, info, chosen, frames=count)
        seconds = time.perf_counter() - started
        for index, picture in enumerate(frames, 1):
            shutil.copyfile(picture, pictures / f"f{index:04d}.png")
        shutil.copyfile(job / "vantage.log", log)
    run = vantage_result(info, chosen, text, tries, seconds, load)
    if len(frames) != count:
        run["notes"].insert(0, f"Vantage 只写出了 {len(frames)} 帧，应为 {count} 帧，视频会变短。")
    return {**run, "log": str(log)}


def run_timeout(chosen, frames):
    """The worker's usual limit for the first frame, plus each further frame's own time limit and export."""
    from .worker_pool import seconds
    return seconds("HOUDINI_RESEARCH_WORKER_TIMEOUT", 600) + (frames - 1) * (chosen.get("time_limit", 540) + 30)


def intact(picture):
    try:
        with Image.open(picture) as im:
            im.load()
        return True
    except (OSError, SyntaxError):
        return False


def animate_karma(path, chosen, camera, first, last, rop, base, pictures):
    """Karma renders the range in runs of up to CHUNK frames, each one worker request and one husk process, so the
    HIP loads, the scene is translated and the shaders compile once per run instead of once per frame. Every run
    uses the camera the first one resolved. A run that stops early (a GPU fault, a husk crash) keeps its finished
    frames and the range continues from the first missing one; two stops in a row without a new frame give up."""
    from .sop_lab import worker
    load = gpu_load() if chosen.get("engine", "xpu") == "xpu" else None
    total = last - first + 1
    run, limited, resumed, seconds, frame, stalled = None, [], [], 0., first, False
    while frame <= last:
        end = min(last, frame + CHUNK - 1)
        info, rows, stopped = None, [], None
        with job_folder("houdini-karma-") as job:
            try:
                info = worker({"action": "karma_render", "hip": str(path), "camera": camera, "frames": [frame, end],
                               "rop": rop, "preset": base, "settings": chosen}, job,
                              timeout=run_timeout(chosen, end - frame + 1))
            except (ValueError, RuntimeError) as exc:
                if run is None:
                    raise  # nothing has rendered: the request itself cannot work (camera, ROP, no GPU)
                stopped = str(exc)
            else:
                rows, stopped = info.pop("frames"), info.pop("stopped", None)
                if stopped and rows and not intact(job / rows[-1]["file"]):
                    rows.pop()  # husk died while writing this frame
                for row in rows:
                    shutil.copyfile(job / row["file"], pictures / f"f{row['frame'] - first + 1:04d}.png")
                shutil.copyfile(job / info.pop("log"), pictures.parent / f"husk-F{frame}.log")
        if info is not None:
            seconds += info["seconds"]
            limited += [row["frame"] for row in rows if row["status"] == "time_limit"]
            camera = info["camera"]
            run = run or info
        if stopped:
            if not rows and stalled:
                raise RuntimeError(f"Karma stopped twice at frame {frame}, after {frame - first} of {total} frames "
                                   f"(kept in {pictures}): {stopped}")
            stalled = not rows
            resumed.append(frame + len(rows))
            time.sleep(RETRY_PAUSE)
        else:
            stalled = False
        frame += len(rows)
    run = {k: v for k, v in run.items() if k != "progress_percent"}
    rows = []
    if run["settings"]["engine"] == "xpu":
        run["gpu_load"] = load
        rows += load_notes(load)
    if limited:
        rows.append(f"{len(limited)} 帧到了时间上限（如 F{limited[0]}），这些帧更噪。")
    if resumed:
        rows.append(f"渲染中途停了 {len(resumed)} 次（如 F{resumed[0]}，多半是显卡或驱动出错），已从缺的那一帧接着渲完。")
    run.update(status="time_limit" if limited else "completed", seconds=round(seconds, 2),
               limited_frames=limited[:50], resumed_at=resumed, log=str(pictures.parent / f"husk-F{first}.log"),
               notes=rows + run["notes"])
    return run


def animate(hip, camera="", frames=None, preset="preview", changes=None, fps=24, rop="", topic="", note=""):
    """Render a frame range into numbered PNGs and, when ffmpeg is installed, an MP4."""
    saved = saved_presets()
    chosen = settings(preset, changes, saved)
    engine = chosen.get("engine", "xpu")
    first, last = frame_range(frames, engine)
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("fps must be a whole number in 1..120")
    path = scene(hip)
    before = sha(path)
    clip = home() / "videos" / uid()
    pictures = clip / "frames"
    pictures.mkdir(parents=True)
    if engine == "vantage":
        run = animate_vantage(path, chosen, camera, first, last, pictures)
    else:
        run = animate_karma(path, chosen, camera, first, last, rop, base_of(preset, saved), pictures)
    stills = sorted(pictures.glob("f*.png"))
    video = vantage.encode(pictures, "f%04d.png", fps, clip / "clip.mp4")
    if video is None:
        run["notes"].append("这台电脑没有 ffmpeg，只保存了逐帧图片；装上 ffmpeg 后可以合成视频。")
    picks = sorted({0, len(stills) // 2, len(stills) - 1})
    sheet = board([(f"F{first + i}", stills[i]) for i in picks], width=426, cols=len(picks))
    sheet.save(clip / "sheet.png")
    text = summary(run) + f"，{len(stills)} 帧，{fps} 帧/秒"
    if engine == "vantage" and run.get("render_seconds"):
        text += f"，每帧渲染约 {run['render_seconds'] / len(stills):.2g} 秒"
    run.pop("frame", None)
    run.update(hip=str(path), hip_unchanged=sha(path) == before, preset=preset, frames=[first, last],
               frame_count=len(stills), fps=fps, folder=str(clip), frames_folder=str(pictures),
               video=str(video) if video else None, sheet=str(clip / "sheet.png"), summary=text)
    if topic.strip():
        card = record("animation", f"{ENGINES.get(engine, engine)} 动画 F{first}–F{last}"[:120],
                      list(dict.fromkeys([topic.strip().lower(), "render"])),
                      (text + ("。" + note.strip() if note.strip() else ""))[:700],
                      {"hip": str(path), "hip_sha256": before, "preset": preset, "request": chosen,
                       "camera": run["camera"], "frames": [first, last], "fps": fps, "folder": str(clip),
                       "video": run["video"]})
        run["record"] = card["id"]
    return run, sheet
