"""Standalone planar kinematics, embedded in saved Houdini guides."""
import math


def four_points(a, d, crank, coupler, rocker, angle, branch):
    theta = math.radians(angle)
    bx = a[0] + crank * math.cos(theta)
    by = a[1] + crank * math.sin(theta)
    dx, dy = d[0] - bx, d[1] - by
    distance = math.hypot(dx, dy)
    if distance <= abs(coupler - rocker) or distance >= coupler + rocker:
        raise ValueError("Four-bar cannot close on a unique branch at %.6g degrees" % angle)
    length = (coupler**2 - rocker**2 + distance**2) / (2 * distance)
    height = math.sqrt(max(0, coupler**2 - length**2))
    sign = 1 if branch == "left" else -1
    c = (bx + (dx * length - sign * dy * height) / distance,
         by + (dy * length + sign * dx * height) / distance)
    return [a, (bx, by), c, d]


def check_fourbar_sweep(spec):
    a, d = spec["ground_a"], spec["ground_d"]
    if math.dist(a, d) == 0:
        raise ValueError("Ground pins must be distinct")
    low, high = sorted((min(k[1] for k in spec["keys"]), max(k[1] for k in spec["keys"])))
    direction = math.degrees(math.atan2(d[1] - a[1], d[0] - a[0]))
    candidates = [low, high]
    for extremum in (direction, direction + 180):
        angle = extremum + 360 * math.ceil((low - extremum) / 360)
        if angle <= high:
            candidates.append(angle)
    for angle in candidates:
        four_points(a, d, spec["crank"], spec["coupler"], spec["rocker"], angle, spec["branch"])


def rope_path(falls, radius, drop):
    if drop <= 2 * radius:
        raise ValueError("Upper and lower sheave blocks need more separation")
    pts = []
    for i in range(falls):
        x = (2*i - falls + 1) * radius
        down = i % 2 == 0
        start, end = (0., -drop) if down else (-drop, 0.)
        if not pts:
            pts.append((x, start))
        pts.append((x, end))
        if i < falls - 1:
            for step in range(1, 25):
                angle = math.pi + (1 if down else -1) * math.pi * step / 24
                pts.append((x + radius + radius * math.cos(angle), end + radius * math.sin(angle)))
    return pts
