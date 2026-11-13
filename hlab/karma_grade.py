"""Develop Karma's linear EXR into the PNG a person looks at: exposure, then a tone curve. Imported inside hython,
which brings numpy and OpenImageIO; the curve itself (agx) needs numpy only.

Karma's own PNG clips everything above 1 to white. AgX rolls highlights off toward white the way film and camera
profiles do, so a sunlit wall keeps its shape and colour."""
import numpy as np

# AgX by Troy Sobotka: inset and outset matrices for Rec.709 primaries and a sigmoid over 16.5 stops of log2.
INSET = np.array([[0.842479062253094, 0.0784335999999992, 0.0792237451477643],
                  [0.0423282422610123, 0.878468636469772, 0.0791661274605434],
                  [0.0423756549057051, 0.0784336, 0.879142973793104]])
OUTSET = np.array([[1.19687900512017, -0.0980208811401368, -0.0990297440797205],
                   [-0.0528968517574562, 1.15190312990417, -0.0989611768448433],
                   [-0.0529716355144438, -0.0980434501171241, 1.15107367264116]])
LOW, HIGH = -12.47393, 4.026069
LUMA = np.array([.2126, .7152, .0722])
# "agx_punchy": a little more contrast and colour than the flat base curve.
PUNCH_POWER, PUNCH_SATURATION = 1.2, 1.45


def agx(rgb, punchy=False):
    """Display values in 0..1 for linear Rec.709 rgb (an array ending in 3)."""
    v = np.clip(rgb, 1e-10, None) @ INSET.T
    v = (np.clip(np.log2(v), LOW, HIGH) - LOW) / (HIGH - LOW)
    x2 = v * v
    x4 = x2 * x2
    v = 15.5 * x4 * x2 - 40.14 * x4 * v + 31.96 * x4 - 6.868 * x2 * v + .4298 * x2 + .1191 * v - .00232
    if punchy:
        v = np.clip(v, 0, None) ** PUNCH_POWER
        luma = v @ LUMA
        v = luma[..., None] + PUNCH_SATURATION * (v - luma[..., None])
    return np.clip(v @ OUTSET.T, 0, 1)


def srgb(rgb):
    """The plain sRGB transfer, clipping above 1: what Karma's own PNG shows."""
    v = np.clip(rgb, 0, 1)
    return np.where(v <= .0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - .055)


def develop(source, target, tone="off", exposure=0., backdrop=None):
    """Write the EXR at source as an 8-bit PNG at target. backdrop, a display colour in 0..1, is laid behind the
    picture after the tone curve, so it shows exactly as given and the PNG is opaque."""
    import OpenImageIO as oiio
    picture = oiio.ImageBuf(str(source))
    spec = picture.spec()
    if picture.has_error or not spec.width:
        raise RuntimeError(f"Cannot read the rendered EXR {source}: {picture.geterror()}")
    pixels = np.asarray(picture.get_pixels(oiio.FLOAT), dtype=np.float64).reshape(spec.height, spec.width, -1)
    names = [name.split(".")[-1].upper() for name in spec.channelnames]
    rgb = pixels[:, :, [names.index(c) for c in "RGB"]] if all(c in names for c in "RGB") else pixels[:, :, :3]
    alpha = np.clip(pixels[:, :, names.index("A")], 0, 1) if "A" in names else np.ones(rgb.shape[:2])
    # Karma stores colour multiplied by coverage; a PNG stores it straight.
    straight = np.where(alpha[..., None] > 1e-6, rgb / np.maximum(alpha[..., None], 1e-6), 0.) * 2. ** exposure
    shown = srgb(straight) if tone == "off" else agx(straight, tone == "agx_punchy")
    if backdrop is not None:
        shown = shown * alpha[..., None] + np.asarray(backdrop, dtype=np.float64) * (1. - alpha[..., None])
        alpha = np.ones_like(alpha)
    out = np.concatenate([shown, alpha[..., None]], axis=2)
    result = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, 4, oiio.UINT8))
    result.set_pixels(oiio.ROI(0, spec.width, 0, spec.height), np.ascontiguousarray(out, dtype=np.float32))
    if not result.write(str(target)):
        raise RuntimeError(f"Cannot write {target}: {result.geterror()}")
