"""Karma presets, bounded controls and husk log reading. Pure Python, shared by hython and the MCP server."""
import math
import re

PRESETS = {
    "preview": {"label": "快速预览", "note": "看构图、灯光方向和材质大致对不对。长边最多 960，32 采样，显卡降噪，30 秒封顶。",
                "settings": {"engine": "xpu", "samples": 32, "denoiser": "optix", "max_edge": 960,
                             "time_limit": 30, "motion_blur": False, "depth_of_field": False}},
    "standard": {"label": "标准试渲", "note": "判断明暗层次、反射和阴影。长边最多 1920，128 采样，显卡降噪，2 分钟封顶。",
                 "settings": {"engine": "xpu", "samples": 128, "denoiser": "optix", "max_edge": 1920, "time_limit": 120}},
    "final": {"label": "正式出图", "note": "相机原分辨率，512 采样，不降噪以保留细节，单帧最长 8 分钟。",
              "settings": {"engine": "xpu", "samples": 512, "denoiser": "off", "max_edge": 8192, "time_limit": 480}},
    "scene": {"label": "工程原设置", "note": "沿用所选 Karma 节点自己的采样和降噪，只改 changes 写明的项，2 分钟封顶。",
              "settings": {"time_limit": 120}},
}

# Lighting looks replace the scene's sky and sun with temporary lights; "scene" keeps the HIP's own lights.
LIGHTING = {
    "scene": {"label": "工程原灯光", "note": "用工程自己的灯，不加不关。"},
    "day": {"label": "日景", "angle": 30., "elevation": 35., "keep_scene_lights": False,
            "note": "晴天：暖白色太阳从右前方照来，加蓝天，影子清楚。太阳越低越暖、影子越长，接近地平线时是日落。"},
    "overcast": {"label": "阴天", "angle": 30., "elevation": 40., "keep_scene_lights": False,
                 "note": "阴天：整片天空发光，头顶最亮，云后太阳那一侧略亮，几乎没有影子，适合看形体和材质。"},
    "night": {"label": "夜景", "angle": -135., "elevation": 30., "keep_scene_lights": True,
              "note": "夜晚：淡蓝色月光从左后方勾出轮廓，夜空比建筑亮一点；保留工程里的点光、聚光、面光等局部灯。"},
    "studio": {"label": "摄影棚", "angle": 30., "elevation": 45., "keep_scene_lights": False,
               "note": "产品摄影棚：大柔光箱做主光和辅光，后方灯条勾边，灰色背景在物体后面最亮；灯按画面里几何体的范围摆放。"},
}
CHOICES = {"engine": ("xpu", "cpu"), "denoiser": ("off", "optix", "oidn"), "lighting": tuple(LIGHTING)}
SWITCHES = ("motion_blur", "depth_of_field", "convert_materials", "keep_scene_lights")
NUMBERS = {
    "samples": (int, 1, 16384), "time_limit": (int, 1, 540), "max_edge": (int, 64, 8192), "width": (int, 16, 8192),
    "resolution_scale": (float, .05, 1.), "diffuse_limit": (int, 0, 64), "reflection_limit": (int, 0, 64),
    "refraction_limit": (int, 0, 64), "volume_limit": (int, 0, 64), "sss_limit": (int, 0, 64),
    "color_limit": (float, .1, 1000.), "light_sampling_quality": (float, .01, 10.),
    "light_angle": (float, -180., 180.), "light_elevation": (float, 0., 90.), "light_exposure": (float, -6., 6.),
    "light_fill": (float, -3., 3.),
}
LIGHT_CONTROLS = ("light_angle", "light_elevation", "light_exposure", "light_fill", "keep_scene_lights")
# Plain control name -> Karma ROP parameter. Resolution and the time limit are applied separately.
PARMS = {
    "engine": "engine", "samples": "pathtracedsamples", "denoiser": "denoiser", "motion_blur": "enablemblur",
    "depth_of_field": "enabledof", "diffuse_limit": "diffuselimit", "reflection_limit": "reflectionlimit",
    "refraction_limit": "refractionlimit", "volume_limit": "volumelimit", "sss_limit": "ssslimit",
    "color_limit": "colorlimit", "light_sampling_quality": "light_sampling_quality",
}
MEANING = {
    "engine": "xpu 用显卡；cpu 用处理器，支持全部 VEX 材质",
    "samples": "每像素采样数，越高越干净、越慢",
    "denoiser": "off 不降噪；optix 显卡降噪（首次使用需准备约 2 分钟）；oidn 处理器降噪",
    "time_limit": "单帧时间上限（秒），到时保存当时的画面",
    "max_edge": "长边像素上限，按相机比例缩小",
    "width": "直接指定宽度，高度按相机比例；会取代预设的长边上限",
    "resolution_scale": "相机分辨率的比例",
    "motion_blur": "运动模糊", "depth_of_field": "景深",
    "convert_materials": "渲染前把 Karma 读不了的旧材质临时转成 MaterialX（默认开）",
    "diffuse_limit": "漫反射反弹次数", "reflection_limit": "反射反弹次数", "refraction_limit": "折射反弹次数",
    "volume_limit": "体积反弹次数", "sss_limit": "次表面散射反弹次数",
    "color_limit": "单次采样亮度上限，压低飞白噪点", "light_sampling_quality": "灯光采样质量",
    "lighting": "灯光预设：scene 用工程自己的灯；day 日景；overcast 阴天；night 夜景；studio 产品摄影棚",
    "light_angle": "太阳、月亮或主光的水平方向（度），以相机为准：0 从相机背后照向物体，90 从画面右侧，-90 从左侧，180 逆光；"
                   "阴天是云后太阳的方向，那一侧天空略亮",
    "light_elevation": "太阳、月亮或主光的高度角（度）；日景时越低越暖、影子越长",
    "light_exposure": "灯光预设整体加减曝光（档），+1 亮一倍，-1 暗一半",
    "light_fill": "补光相对主光加减（档）：日景、夜景是天光，摄影棚是辅光；-1 影子更暗、反差更大，+1 影子更亮、更柔；阴天不用",
    "keep_scene_lights": "保留工程里的点光、聚光、面光等局部灯（夜景默认保留，其余默认关掉）；工程里的天空和太阳类灯总会被替换",
}


def controls():
    rows = {}
    for name, meaning in MEANING.items():
        if name in CHOICES:
            rows[name] = f"{meaning}（{' / '.join(CHOICES[name])}）"
        elif name in NUMBERS:
            _, low, high = NUMBERS[name]
            rows[name] = f"{meaning}（{low:g}–{high:g}）"
        else:
            rows[name] = f"{meaning}（true / false）"
    return rows


def checked(changes):
    out = {}
    for name, value in (changes or {}).items():
        if name in CHOICES:
            if value not in CHOICES[name]:
                raise ValueError(f"{name} must be one of: {', '.join(CHOICES[name])}")
        elif name in SWITCHES:
            if type(value) is not bool:
                raise ValueError(f"{name} must be true or false")
        elif name in NUMBERS:
            kind, low, high = NUMBERS[name]
            if (type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high
                    or kind is int and not float(value).is_integer()):
                raise ValueError(f"{name} must be {'an integer' if kind is int else 'a number'} in {low:g}..{high:g}")
            value = kind(value)
        else:
            raise ValueError(f"Unsupported Karma control {name!r}. Supported: {', '.join(MEANING)}")
        out[name] = value
    return out


def settings(preset, changes=None, saved=None):
    saved = saved or {}
    if preset in PRESETS:
        base = dict(PRESETS[preset]["settings"])
    elif preset in saved:
        entry = saved[preset]
        base = settings(entry["base"], entry["changes"])
    else:
        raise ValueError(f"Unknown preset {preset!r}. Choose one of: {', '.join([*PRESETS, *saved])}")
    changes = checked(changes)
    if "width" in changes and "max_edge" not in changes:
        base.pop("max_edge", None)
    chosen = {**base, **changes}
    look = chosen.get("lighting", "scene")
    loose = [name for name in LIGHT_CONTROLS if name in chosen]
    if look == "scene" and loose:
        raise ValueError(f"{', '.join(loose)} only apply with lighting = day, overcast, night or studio")
    if look == "overcast" and "light_fill" in chosen:
        raise ValueError("overcast light is all sky, with no key light to fill against; drop light_fill")
    return chosen


def lighting(chosen):
    """The look a render uses, with each default filled in; None keeps the scene's own lights."""
    look = chosen.get("lighting", "scene")
    if look == "scene":
        return None
    spec = LIGHTING[look]
    out = {"look": look, "label": spec["label"], "exposure": chosen.get("light_exposure", 0.),
           "keep_scene_lights": chosen.get("keep_scene_lights", spec["keep_scene_lights"]),
           "angle": chosen.get("light_angle", spec["angle"]), "elevation": chosen.get("light_elevation", spec["elevation"])}
    if look != "overcast":
        out["fill"] = chosen.get("light_fill", 0.)
    return out


def resolution(camera, chosen):
    width, height = camera
    if width < 1 or height < 1:
        raise ValueError("The camera resolution must be positive")
    w = chosen["width"] if "width" in chosen else width * chosen.get("resolution_scale", 1.)
    if chosen.get("max_edge"):
        w = min(w, chosen["max_edge"] * width / max(width, height))
    w = max(16, round(w))
    return w, max(16, round(w * height / width))


def read_log(stdout, stderr=""):
    info = {"saved": "Saved Image:" in stdout, "time_limit_reached": bool(re.search(r"Run time \d+ exceeded", stderr))}
    size = re.search(r">>> Render .* - (\d+)x(\d+)", stdout)
    if size:
        info["resolution"] = [int(size.group(1)), int(size.group(2))]
    wall = re.findall(r"Total Wall Clock Time: (\d+):(\d+):([\d.]+)", stdout)
    if wall:
        h, m, s = wall[-1]
        info["husk_seconds"] = round(int(h) * 3600 + int(m) * 60 + float(s), 2)
    peak = re.findall(r"Peak Memory Usage: ([\d.]+ \w+)", stdout)
    if peak:
        info["peak_memory"] = peak[-1]
    # Progress lines are periodic, so a quick frame may log only 0%; this matters when a time limit stops it.
    progress = re.findall(r"^\[[\d:]+\]\s+([\d.]+)% Lap=", stdout, re.M)
    info["progress_percent"] = float(progress[-1]) if progress else None
    devices = []
    for block in re.split(r"\nDevice \d+\s*\n", stdout)[1:]:
        kind = re.search(r"^Type\s*:\s*(.+)$", block, re.M)
        name = re.search(r"^Name\s*:\s*(.+)$", block, re.M)
        share = re.search(r"^Contrib\s*:\s*([\d.]+)%", block, re.M)
        if kind and name and share:
            devices.append({"type": kind.group(1).strip(), "name": name.group(1).strip(),
                            "contribution_percent": float(share.group(1))})
    info["devices"] = devices
    info["gpu_verified"] = any(d["type"].lower() == "optix" and d["contribution_percent"] > 0 for d in devices)
    notes = []
    for line in (stdout + "\n" + stderr).splitlines():
        text = re.sub(r"^\[[\d:]+\]\s*", "", line).strip()
        # husk 20.5 may crash on exit after a time-limited frame; the saved image is still valid.
        if info["time_limit_reached"] and "Segmentation fault" in text:
            continue
        if re.search(r"\b(warning|error)\b", text, re.I) and not text.startswith(("+0x", '"')) and text not in notes:
            notes.append(text[:200])
    info["log_warnings"] = notes[:8]
    return info


def excerpt(stdout, stderr, limit=12):
    lines = [re.sub(r"^\[[\d:]+\]\s*", "", l).strip() for l in (stderr + "\n" + stdout).splitlines()]
    lines = [l for l in lines if l and not l.startswith(("+0x", "OTHER THREAD", "CURRENT THREAD", '"'))]
    failing = [l for l in lines if re.search(r"error|fail|fatal|unable|cannot|missing", l, re.I)]
    return " | ".join((failing or lines)[-limit:])
