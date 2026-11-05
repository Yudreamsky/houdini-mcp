"""Physically based material checks for photoreal renders. Pure Python, shared by hython and the MCP server.

A material is described with the same few numbers whatever its node type: base_color (the albedo, base weight
included), metalness, roughness, specular (1 is an ordinary dielectric's 4% reflection at IOR 1.5) and transmission.
Values driven by a texture are left out, since only the constant is known here."""

# Real albedos run from about 0.03 (charcoal, fresh asphalt) to about 0.9 (fresh snow); white paint is about 0.8.
BRIGHTEST, DARKEST = .9, .02
BRIGHT_TARGET, DARK_TARGET = .85, .03
# Polished metal is about 0.05 rough; nothing is perfectly smooth.
SMOOTHEST, SMOOTH_TARGET = .02, .05
# Metals reflect at least about half the light (iron 0.56, aluminium 0.91, gold and copper about 0.95 in red).
METAL_FLOOR = .5


def luminance(c):
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def issues(m):
    """Problems a physically based renderer will show as unreal, as (code, plain-Chinese reason) pairs."""
    found = []
    clear = m.get("transmission", 0.) >= .5
    metal = m.get("metalness", 0.) >= .5
    base = m.get("base_color")
    if base is not None and not clear:
        if not metal and max(base) > BRIGHTEST:
            found.append(("too_bright", f"底色最亮的通道是 {max(base):.2f}，比真实材料亮（白色涂料约 0.8，最白的雪约 0.9）"))
        if not metal and luminance(base) < DARKEST:
            found.append(("too_dark", f"底色亮度只有 {luminance(base):.3f}，比真实材料暗（最黑的炭、沥青约 0.03）"))
        if metal and max(base) < METAL_FLOOR:
            found.append(("dark_metal", f"金属颜色最亮只有 {max(base):.2f}；真实金属的反射率多在 0.5 以上（铁约 0.56，铝约 0.91）"))
    if m.get("specular") is not None and not metal and not clear and m["specular"] < .1:
        found.append(("no_reflection", "完全不反光；现实中的非金属都会反射约 4% 的光（Principled reflect 0.5，MaterialX specular 1）"))
    if m.get("roughness") is not None and m["roughness"] < SMOOTHEST:
        found.append(("mirror_smooth", f"粗糙度 {m['roughness']:.2f}，像绝对光滑的镜面；现实中没有，抛光金属约 0.05–0.15"))
    if .1 < m.get("metalness", 0.) < .9:
        found.append(("half_metal", f"金属度 {m['metalness']:.2f}；材料要么是金属（1）要么不是（0），中间值只适合锈迹、灰尘等过渡"))
    return found


def fixed(m):
    """Corrected values for the issues that have one safe fix, and what changed. half_metal is left for the author."""
    out, changes = dict(m), []
    codes = {code for code, _ in issues(m)}
    base = m.get("base_color")
    if "too_bright" in codes:
        k = BRIGHT_TARGET / max(base)
        out["base_color"] = tuple(c * k for c in base)
        changes.append(f"底色按比例压到最亮 {BRIGHT_TARGET}")
    if "too_dark" in codes:
        lum = luminance(base)
        out["base_color"] = tuple(c * DARK_TARGET / lum for c in base) if lum > 1e-6 else (DARK_TARGET,) * 3
        changes.append(f"底色提到亮度 {DARK_TARGET}")
    if "dark_metal" in codes:
        k = METAL_FLOOR / max(max(base), 1e-6)
        out["base_color"] = tuple(min(1., c * k) for c in base) if max(base) > 1e-6 else (METAL_FLOOR,) * 3
        changes.append(f"金属颜色提到最亮 {METAL_FLOOR}")
    if "no_reflection" in codes:
        out["specular"] = 1.
        changes.append("加上 4% 的反射")
    if "mirror_smooth" in codes:
        out["roughness"] = SMOOTH_TARGET
        changes.append(f"粗糙度提到 {SMOOTH_TARGET}")
    return out, changes
