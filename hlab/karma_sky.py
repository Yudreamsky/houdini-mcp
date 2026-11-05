"""Lighting looks for Karma test renders: camera-relative directions, light levels and sky images. Pure Python.

Levels, colours and placements follow photographers' and lighting artists' practice (the skill's
references/lighting.md) and were checked on Karma renders of white boxes, an 18% grey ball and a chrome ball."""
import math
from functools import lru_cache

# Measured in Karma 20.5 (CPU and XPU agree) as the pixel value of a white matte surface per unit of light:
# a distant light of intensity 1 straight on gives 2.0; a sky image of radiance 1 over the upper half gives 1.0;
# a rectangle light (radiance 1, area not normalised) gives its geometric form factor, from 1 x 1 at distance 10 to
# 8 x 8 at 4.5, and a surface turned away from it the cosine of that angle.
DISTANT_GAIN = 2.
AREA_GAIN = 1.
# What a white matte surface shows from each light of a look (1.0 clips: Karma applies no tone curve).
# day: "sun" faces an overhead sun (a lower sun is dimmer); "sky" is open ground lit by the sky alone, sun at 40 degrees.
# overcast: open ground; walls get about half. night: a surface facing the moon, and open ground under the sky.
# studio: a surface facing each softbox; "backdrop" is the background just behind the subject.
# "ground" is the albedo of the ground seen below the horizon.
LEVELS = {
    "day": {"sun": .82, "sky": .14, "ground": .2},
    "overcast": {"sky": .9, "ground": .2},
    "night": {"moon": .14, "sky": .03, "ground": .2},
    "studio": {"key": .75, "fill": .25, "rim": .6, "backdrop": .22},
}
# Colour temperatures as photographed with a daylight white balance (6500 K renders white): the sun warm white high up
# and orange near the horizon, moonlight pale blue by convention, overcast faintly cool.
SUN_KELVIN = ((0., 2100.), (5., 3000.), (10., 3950.), (20., 4900.), (30., 5350.), (40., 5600.), (60., 5900.))
MOON_KELVIN = 8000.
OVERCAST_KELVIN = 6800.
# Clear sky: pale at the horizon, deep blue overhead, whiter toward the sun. Lighting artists keep the sky's light in
# shadows at 10000 K or below; Karma ignores the switches that would let a bluer visible sky shed paler light, so this
# sky sheds about 12000 K, which keeps it reading blue without a tone curve. Night: blue-grey, the zenith half as bright.
HORIZON_KELVIN = 7000.
ZENITH = (.07, .22, .64)
NIGHT_SKY = ((.036, .040, .048), (.016, .020, .032))
GROUND = (1.05, .98, .88)
# CIE standard skies (ISO 15469) as gradation a, b and scattering c, d, e. Type 12, the clear sky, is darkest about
# 90 degrees from the sun with its horizon 2-5 times the zenith; type 2 is overcast, the zenith three times the
# horizon, slightly brighter toward the hidden sun so that the sides facing it read lighter.
CIE = {"day": (-1., -.32, 10., -3., .45), "overcast": (4., -.7, 2., -1.5, .15)}
# Studio rig relative to the key: name, angle offset, elevation (None follows the key), size and distance in subject
# radii. Key and fill are large softboxes about 48 degrees across; the rim is a 1:5 strip behind the subject on the
# shadow side, which sets tops apart from fronts and outlines edges. It stays 45 degrees off the line behind the subject,
# where glossy tops would mirror it as a white sheet, and fairly high: Karma ignores the shadow switch and light masks of
# /obj lights, and a low rim lays long second shadows across the floor toward the camera.
RIG = (("KEY", 0., None, (4., 4.), 4.5), ("FILL", -90., 20., (4., 4.), 4.5), ("RIM", -165., 35., (.6, 3.), 4.5))
# Studio backdrop: the darkest part (far from the view) relative to the brightest, just behind the subject, and how
# many stops darker the picture's corners are. 2 ** -stops must stay above the darkest part.
BACKDROP = (.18, 2.)
DISC = .53  # degrees across the sun or moon: crisp shadows that still soften with distance, as in a photograph
HAZE = .35  # below the horizon the sky fades into the ground over about 20 degrees, so no wall shows behind a scene


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def gap(a, b):
    """Angle between two unit vectors, in radians."""
    return math.acos(max(-1., min(1., dot(a, b))))


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def grey(v):
    return v, v, v


def luminance(c):
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def chroma(c):
    """The colour scaled to luminance 1."""
    return tuple(v / luminance(c) for v in c)


@lru_cache(maxsize=None)
def kelvin(temperature):
    """Linear RGB of a black body relative to 6500 K (which is white), at luminance 1."""
    def rgb(t):
        # Planckian locus (Kim et al. 2002), then CIE XYZ to linear sRGB.
        if t >= 4000:
            x = -3.0258469e9 / t ** 3 + 2.1070379e6 / t ** 2 + .2226347e3 / t + .240390
            y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - .37001483
        else:
            x = -.2661239e9 / t ** 3 - .2343589e6 / t ** 2 + .8776956e3 / t + .179910
            y = (-.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - .16748867 if t >= 2222 else
                 -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - .20219683)
        big_x, big_z = x / y, (1. - x - y) / y
        return (3.2406 * big_x - 1.5372 - .4986 * big_z, -.9689 * big_x + 1.8758 + .0415 * big_z,
                .0557 * big_x - .2040 + 1.0570 * big_z)
    t = min(max(temperature, 1667.), 25000.)
    return chroma(tuple(max(0., a / b) for a, b in zip(rgb(t), rgb(6500.))))


def interpolate(table, x):
    """Piecewise-linear lookup in (x, y) pairs, held flat beyond the ends."""
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def air_mass(elevation):
    """Kasten-Young relative air mass: 1 overhead, about 38 at the horizon."""
    h = max(elevation, 0.)
    return 1. / (math.sin(math.radians(h)) + .50572 * (h + 6.07995) ** -1.6364)


def sunlight(elevation):
    """Colour (luminance 1) and brightness (overhead 1) of direct sun: it dims and warms as it sinks."""
    mired = interpolate([(e, 1e6 / k) for e, k in SUN_KELVIN], elevation)
    return kelvin(1e6 / mired), math.exp(-.21 * (air_mass(elevation) - 1.))


def sky_scale(elevation):
    """Clear-sky brightness relative to a 40-degree sun: a low sun leaves a dimmer sky."""
    return (max(math.sin(math.radians(elevation)), .02) / math.sin(math.radians(40.))) ** .6


def form_factor(width, height, distance):
    """Cosine-weighted share of the hemisphere a rectangle covers, seen from a point facing its centre."""
    x, y = width / 2. / distance, height / 2. / distance
    a, b = math.sqrt(1 + x * x), math.sqrt(1 + y * y)
    return 2. / math.pi * (x / a * math.atan(y / a) + y / b * math.atan(x / b))


def camera_frame(forward, up):
    """Level forward and right vectors of a camera; one looking straight down uses its picture's up as forward."""
    flat = (forward[0], 0., forward[2])
    if math.hypot(flat[0], flat[2]) < 1e-4:
        flat = (up[0], 0., up[2])
    f = unit(flat)
    return f, (-f[2], 0., f[0])


def toward(frame, angle, elevation):
    """Unit vector from the subject to a light: angle 0 is behind the camera, 90 camera-right, 180 behind the subject."""
    (fx, _, fz), (rx, _, rz) = frame
    a, e = math.radians(angle), math.radians(elevation)
    level = (-math.cos(a) * fx + math.sin(a) * rx, -math.cos(a) * fz + math.sin(a) * rz)
    return math.cos(e) * level[0], math.sin(e), math.cos(e) * level[1]


def plan(look, frame, angle=0., elevation=0., fill=0.):
    """The look's lights: directions from the camera frame, colours and intensities from the calibrated levels.
    fill (stops) scales the studio fill light; the sky that fills day and night shadows is scaled in sky_image."""
    level = LEVELS[look]
    if look in ("day", "night"):
        if look == "day":
            color, strength = sunlight(elevation)
            head_on = level["sun"] * strength
        else:
            color, head_on = kelvin(MOON_KELVIN), level["moon"]
        return [{"name": "SUN" if look == "day" else "MOON", "type": "sun", "toward": toward(frame, angle, elevation),
                 "color": color, "intensity": head_on / (DISTANT_GAIN * luminance(color)), "head_on": head_on,
                 "elevation": elevation}]
    if look == "studio":
        return [{"name": name, "type": "grid", "toward": toward(frame, angle + offset, elevation if height is None else height),
                 "color": (1., 1., 1.), "size": size, "distance": distance,
                 "intensity": level[name.lower()] * (2. ** fill if name == "FILL" else 1.) / (AREA_GAIN * form_factor(*size, distance))}
                for name, offset, height, size, distance in RIG]
    return []


def direction(u, v):
    """World direction of a lat-long pixel as a Houdini/Karma environment light maps it: top is +Y, u=0.5 is -Z."""
    phi, h = (u - .5) * 2. * math.pi, (.5 - v) * math.pi
    return math.sin(phi) * math.cos(h), math.sin(h), -math.cos(phi) * math.cos(h)


def cie(kind, d, sun):
    """Relative luminance of a CIE standard sky toward d (up is +Y), with the sun toward `sun`."""
    a, b, c, dd, e = CIE[kind]
    up = max(d[1], 0.)
    gradation = 1. + a * math.exp(b / up) if up > 1e-3 else 1.
    chi = gap(d, sun)
    return gradation * (1. + c * (math.exp(dd * chi) - math.exp(dd * math.pi / 2.)) + e * math.cos(chi) ** 2)


def sky_shape(look, d, sun=None, view=None):
    """Relative radiance of the look's sky toward d, before its level is applied."""
    if look == "studio":
        forward, corner = view
        floor, stops = BACKDROP
        # A soft pool of light behind the subject that is `stops` darker at the picture's corners.
        spread = corner / math.sqrt(math.log((1. - floor) / (2. ** -stops - floor)))
        return grey(floor + (1. - floor) * math.exp(-(gap(d, forward) / spread) ** 2))
    h = max(d[1], 0.)
    if look == "overcast":
        return tuple(c * cie("overcast", d, sun["toward"]) for c in kelvin(OVERCAST_KELVIN))
    if look == "day":
        # Pale at the horizon, deep blue higher up and away from the sun, whiter and warmer toward it: the bright sky
        # round the sun keeps the light shed into shadows near 12000 K while the sky in view still reads blue.
        chi = gap(d, sun["toward"])
        tint = mix(mix(kelvin(HORIZON_KELVIN), chroma(ZENITH), h ** .45 * math.sin(chi) ** .5), sun["color"], math.exp(-chi))
        return tuple(c * cie("day", d, sun["toward"]) for c in tint)
    horizon, zenith = NIGHT_SKY
    halo = .6 * math.exp(-gap(d, sun["toward"]) / .05) * max(horizon) / max(sun["color"])  # a small halo round the moon
    return tuple(b + halo * c for b, c in zip(mix(horizon, zenith, h ** .5), sun["color"]))


def sky_image(look, sun=None, view=None, fill=0., width=256, height=128):
    """Rows of linear RGB, top first, for the look's environment light. Skies are scaled so that open ground shows the
    look's sky level (times 2 ** fill); the studio backdrop so that its brightest part shows the backdrop level."""
    level = LEVELS[look]
    rows = [[direction((i + .5) / width, (j + .5) / height) for i in range(width)] for j in range(height)]
    shaped = [[sky_shape(look, d, sun, view) for d in row] for row in rows]
    if look == "studio":
        scale, ground = level["backdrop"], None
    else:
        # Cosine-weighted mean over the upper half: what an upward-facing white matte surface shows.
        step = 2. * math.pi / width * math.pi / height
        seen = sum(luminance(c) * d[1] * math.sqrt(1. - d[1] * d[1]) * step
                   for row, cols in zip(rows, shaped) for d, c in zip(row, cols) if d[1] > 0) / math.pi
        target = level["sky"] * (sky_scale(sun["elevation"]) if look == "day" else 1.) * 2. ** fill
        direct = sun.get("head_on", 0.) * math.sin(math.radians(sun["elevation"]))
        ground = tuple(c * level["ground"] * (direct + target) for c in GROUND)
        scale = target / seen

    def pixel(d, col):
        lit = tuple(c * scale for c in col)
        if ground is None or d[1] >= 0:
            return lit
        # Below the horizon the shape holds the horizon's colour, which hazes into the ground.
        t = min(1., -d[1] / HAZE)
        return mix(lit, ground, t * t * (3 - 2 * t))
    return [[pixel(d, col) for d, col in zip(row, cols)] for row, cols in zip(rows, shaped)]


def design(look, frame, angle=0., elevation=0., fill=0., view=None):
    """The look's lights and sky image. view is the camera's unit view vector and the angle from it to the picture's
    corner (radians), which centre the studio backdrop behind the subject."""
    lights = plan(look, frame, angle, elevation, fill)
    if look == "studio":
        return lights, sky_image(look, view=view or (frame[0], math.radians(25.)))
    sun = lights[0] if lights else {"toward": toward(frame, angle, elevation), "elevation": elevation}
    return lights, sky_image(look, sun, fill=fill)


def write_hdr(path, rows):
    """Write linear RGB rows as an uncompressed Radiance RGBE image (Karma reads it on CPU and XPU)."""
    body = bytearray()
    for row in rows:
        for r, g, b in row:
            m = max(r, g, b)
            if m < 1e-30:
                body += b"\0\0\0\0"
                continue
            mantissa, exponent = math.frexp(m)
            scale = mantissa * 256. / m
            body += bytes((int(r * scale), int(g * scale), int(b * scale), exponent + 128))
    path.write_bytes(f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {len(rows)} +X {len(rows[0])}\n".encode() + bytes(body))


def read_hdr(path):
    """Rows of linear RGB, top first, from a flat RGBE file as write_hdr makes it."""
    body = path.read_bytes().split(b"\n\n", 1)[1]
    size, pixels = body.split(b"\n", 1)
    _, height, _, width = size.split()
    values = [tuple(c * 2. ** (e - 136) for c in pixels[i:i + 3]) if e else (0., 0., 0.)
              for i, e in ((i, pixels[i + 3]) for i in range(0, len(pixels), 4))]
    return [values[r * int(width):(r + 1) * int(width)] for r in range(int(height))]


def lookup(rows, d):
    """The sky's linear colour toward unit direction d, interpolated between pixels."""
    height, width = len(rows), len(rows[0])
    x = ((math.atan2(d[0], -d[2]) / (2. * math.pi) + .5) % 1.) * width - .5
    y = min(max((.5 - math.asin(max(-1., min(1., d[1]))) / math.pi) * height - .5, 0.), height - 1.)
    x0, y0 = math.floor(x), math.floor(y)
    tx, ty = x - x0, y - y0
    x0, x1, y1 = x0 % width, (x0 + 1) % width, min(y0 + 1, height - 1)
    top = mix(rows[y0][x0], rows[y0][x1], tx)
    return mix(top, mix(rows[y1][x0], rows[y1][x1], tx), ty)
