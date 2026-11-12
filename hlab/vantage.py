"""Render with Chaos Vantage from the MCP server: vantage_console renders a USD file the hython worker exported, its
own log gives the timings, and the look's sky goes behind the result (a USD dome lights a Vantage scene but never
shows behind it). Pure Python plus Pillow; Vantage itself needs its licence and a ray-tracing GPU."""
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .karma_sky import lookup, read_hdr, unit

DEFAULT = Path(r"C:\Program Files\Chaos\Vantage\vantage_console.exe")
# Vantage 3.3 sometimes stops with an access violation while starting (about 1 launch in 8, twice in a row once);
# starting it again works.
CRASHED = (3221225477, -1073741819)
TRIES = 3
SKY_GRID = 96  # columns of the sky computed per frame; the sky is smooth, so it is enlarged to the picture


def executable():
    path = Path(os.environ.get("HOUDINI_RESEARCH_VANTAGE", DEFAULT))
    if not path.is_file():
        raise ValueError("Chaos Vantage is not installed here (no vantage_console.exe); set HOUDINI_RESEARCH_VANTAGE "
                         "to its path, or use engine xpu or cpu")
    return path


def arguments(scene, output, size, camera, chosen, view, log, frames=0):
    """vantage_console arguments for a still, or for a sequence of frames counted from the stage's start."""
    args = [f"-sceneFile={scene}", f"-outputFile={output}", f"-outputWidth={size[0]}", f"-outputHeight={size[1]}",
            f"-camera={camera}", f"-samples={chosen.get('samples', 64)}",
            f"-denoiser={'false' if chosen.get('denoiser') == 'off' else 'true'}",
            f"-motionBlur={'true' if chosen.get('motion_blur') else 'false'}",
            "-autoExposure=false", "-pngAlpha=true", "-autoClose=true", "-skipHome", f"-debugLogFile={log}"]
    if view["projection"] == "orthographic":
        # Vantage misreads a USD orthographic camera's width; it takes this one in scene units.
        args += ["-cameraType=5", f"-cameraOrthoWidth={view['ortho_width']:g}"]
    if frames:
        args += [f"-frames=0-{frames - 1}", "-antiFlicker=true"]
    return args


def launch(args, timeout):
    """Run vantage_console, starting it again after a start-up crash; returns the number of tries."""
    from .worker_pool import kill_tree
    for attempt in range(1, TRIES + 1):
        proc = subprocess.Popen([str(executable()), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            raise RuntimeError(f"Vantage did not finish within {timeout} s; check that it is licensed and that no "
                               "dialog is waiting on screen") from None
        if code == 0:
            return attempt
        if code not in CRASHED or attempt == TRIES:
            raise RuntimeError(f"Vantage stopped with exit code {code}"
                               + (f" on all {TRIES} tries" if code in CRASHED else ""))
    return TRIES


def minutes(text):
    m = re.match(r"(?:(\d+)m\s*)?(\d+)s", text.strip())
    return int(m.group(1) or 0) * 60 + int(m.group(2)) if m else None


def read_log(text):
    """Timings, scene size and GPU from a Vantage debug log."""
    info = {}
    if m := re.search(r"Chaos Vantage v([\d.]+)", text):
        info["vantage_version"] = m.group(1)
    if m := re.search(r"Device #0: ([^,]+), (\d+) MB", text):
        info["gpu"] = m.group(1)
    if m := re.search(r"Total initialization time: ([\d.]+) seconds", text):
        info["startup_seconds"] = float(m.group(1))
    stills = [float(v) for v in re.findall(r"HQ image rendered in ([\d.]+) seconds", text)]
    if stills:
        info["render_seconds"] = round(sum(stills), 3)
    if m := re.search(r"Complete HQ sequence of (\d+) frames rendered in ([\dms ]+)", text):
        info.update(frames_rendered=int(m.group(1)), render_seconds=minutes(m.group(2)))
    if m := re.search(r"Loaded '[^']*' \| (\d+) Lights \| (\d+) Nodes \| ([\d.]+) (thousand |million )?Unique vertices", text):
        scale = {"thousand ": 1e3, "million ": 1e6}.get(m.group(4) or "", 1)
        info["scene"] = {"lights": int(m.group(1)), "nodes": int(m.group(2)), "vertices": round(float(m.group(3)) * scale)}
    errors = [line.split("] ", 1)[-1] for line in text.splitlines() if "[err]" in line or "ERROR" in line]
    if errors:
        info["log_errors"] = errors[:5]
    return info


def srgb(value):
    v = min(1., max(0., value))
    return round(255. * (v * 12.92 if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055))


LINEAR = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in (i / 255. for i in range(256))]


def ray(matrix, local):
    """World direction of a camera-space direction, with Houdini's row-vector matrices."""
    return unit(tuple(sum(local[i] * matrix[i][j] for i in range(3)) for j in range(3)))


def backdrop(rows, view, frame, size):
    """The sky the camera sees, as an RGBA image of the picture's size."""
    matrix = view["matrices"][str(frame)]
    if view["projection"] == "orthographic":
        return Image.new("RGBA", size, tuple(srgb(c) for c in lookup(rows, ray(matrix, (0., 0., -1.)))) + (255,))
    cols = SKY_GRID
    lines = max(2, round(cols * size[1] / size[0]))
    small = Image.new("RGB", (cols, lines))
    half, tall = view["tan_half"], view["tan_half"] * view["aspect"]
    small.putdata([tuple(srgb(c) for c in lookup(rows, ray(matrix, (((i + .5) / cols * 2. - 1.) * half,
                                                                     (1. - (j + .5) / lines * 2.) * tall, -1.))))
                   for j in range(lines) for i in range(cols)])
    return small.resize(size, Image.Resampling.BICUBIC).convert("RGBA")


def with_sky(picture, rows, view, frame):
    """The render over its sky. Vantage stores colours premultiplied by alpha in linear light, so a partly covered
    edge pixel is its own colour plus the sky behind the uncovered part; blending it again would darken every
    silhouette and the horizon."""
    front = Image.open(picture).convert("RGBA")
    out = backdrop(rows, view, frame, front.size).convert("RGB")
    alpha = front.getchannel("A")
    out.paste(front.convert("RGB"), mask=alpha.point(lambda a: 255 if a == 255 else 0))
    width, colours, sky = front.width, front.load(), out.load()
    for index, a in enumerate(alpha.tobytes()):
        if 0 < a < 255:
            x, y = index % width, index // width
            behind = 1. - a / 255.
            sky[x, y] = tuple(srgb(LINEAR[c] + LINEAR[s] * behind) for c, s in zip(colours[x, y][:3], sky[x, y]))
    return out


def run(folder, info, chosen, frames=0):
    """Render the exported scene in folder; returns pictures (sky behind when the look has one), log text and tries."""
    out = folder / "vantage"
    out.mkdir(exist_ok=True)
    log = folder / "vantage.log"
    args = arguments(folder / info["usd"], out / "frame.png", info["resolution"], info["camera_name"], chosen,
                     info["view"], log, frames)
    tries = launch(args, 300 + 30 * max(frames, 1))
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    pictures = sorted(out.glob("frame*.png"))
    if not pictures:
        raise RuntimeError("Vantage finished without writing an image" + (": " + "; ".join(read_log(text).get("log_errors", []))
                                                                          if text else ""))
    if info.get("sky"):
        rows = read_hdr(folder / info["sky"])
        first = info["frames"][0]
        for index, picture in enumerate(pictures):
            with_sky(picture, rows, info["view"], first + index).save(picture)
    return pictures, text, tries


def encode(frames_folder, pattern, fps, target):
    """An H.264 video from numbered frames, when ffmpeg is on PATH; returns the path or None."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_folder / pattern),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                    str(target)], check=True, timeout=600)
    return target


def summary_seconds(info):
    parts = [f"渲染 {info['render_seconds']:g} 秒"] if info.get("render_seconds") is not None else []
    if info.get("startup_seconds") is not None:
        parts.append(f"启动 {info['startup_seconds']:g} 秒")
    if info.get("export_seconds") is not None:
        parts.append(f"导出 {info['export_seconds']:g} 秒")
    return "（" + "，".join(parts) + "）" if parts else ""
