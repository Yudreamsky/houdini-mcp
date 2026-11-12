"""Karma test renders of saved HIPs: named presets, bounded size and time, searchable evidence."""
import math
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .karma_spec import LIGHTING, PRESETS, checked, controls, settings
from .storage import created_now, home, read, record, sha, uid, write

SAMPLE = "karma-probe"


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


def load_notes(load):
    """Warn when other programs hold the GPU before an XPU render."""
    if not load:
        return []
    rows = []
    if load["utilization_percent"] >= 70:
        rows.append(f"开始渲染时显卡使用率已有 {load['utilization_percent']:g}%（其他程序在用，例如本地 AI 模型），"
                    "XPU 可能变慢或到时间上限；急用时可改 engine=cpu。")
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


def run_one(path, chosen, camera, frame, rop, base=""):
    from .sop_lab import worker
    load = gpu_load() if chosen.get("engine", "xpu") == "xpu" else None
    with job_folder("houdini-karma-") as job:
        info = worker({"action": "karma_render", "hip": str(path), "camera": camera, "frame": frame,
                       "rop": rop, "preset": base, "settings": chosen}, job)
        if info["settings"]["engine"] == "xpu":
            info.update(gpu_load=load, notes=load_notes(load) + info["notes"])
        info["notes"] = progress_note(info) + info["notes"]
        image_id = uid()
        target = home() / "images" / (image_id + ".png")
        log = home() / "karma" / "logs" / (image_id + ".log")
        for folder in (target.parent, log.parent):
            folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(job / info.pop("file"), target)
        shutil.copyfile(job / info.pop("log"), log)
    return {**info, "image_id": image_id, "sha256": sha(target), "path": str(target), "log": str(log)}


def sample(run):
    keys = ("image_id", "sha256", "frame", "camera", "resolution", "seconds", "status", "settings", "gpu_verified")
    return {k: run[k] for k in keys}


def summary(run):
    s = run["settings"]
    text = f"{s['engine'].upper()} {run['resolution'][0]}×{run['resolution'][1]}，{s['samples']} 采样，降噪 {s['denoiser']}，用时 {run['seconds']:g} 秒"
    if s["engine"] == "xpu":
        share = sum(d["contribution_percent"] for d in run["devices"] if d["type"].lower() == "optix")
        text += f"，显卡贡献 {share:g}%"
    if run.get("materials") and run["materials"]["converted"]:
        text += f"，临时转换材质 {len(run['materials']['converted'])} 个"
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
    text = f"{name} · {run['seconds']:g} 秒 · {s['samples']} 采样 · 降噪 {s['denoiser']} · {w}×{h}"
    if s.get("lighting", "scene") != "scene":
        text += f" · {LIGHTING[s['lighting']]['label']}"
    return text + (" · 到时限" if run["status"] == "time_limit" else "")


def contact(runs, zoom=None, width=640):
    font = label_font()
    tiles = []
    for name, run in runs.items():
        im = flatten(run["path"], zoom=zoom)
        scale = width / im.width
        # Enlarged crops keep their real pixels so noise stays visible.
        im = im.resize((width, max(1, round(im.height * scale))),
                       Image.Resampling.NEAREST if scale > 1 else Image.Resampling.LANCZOS)
        tiles.append((caption(name, run), im))
    cols = 1 if len(tiles) == 1 else 2
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
