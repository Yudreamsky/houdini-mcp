# Installed as the code of the TRAILS Python SOP. Its input is a Scatter SOP.
import math
import hou

node = hou.pwd()
geo = node.geometry()
directions = [point.position().normalized() for point in geo.points()]
geo.clear()
color = geo.addAttrib(hou.attribType.Point, "Cd", (1.0, 1.0, 1.0))
frame = node.evalParm("tick")
age = (frame - node.evalParm("burst_frame")) / 24.0
speed = node.evalParm("speed")
drag = node.evalParm("drag")
gravity = node.evalParm("gravity")
trail = node.evalParm("trail")
delay = node.evalParm("second_delay")
tint = node.evalParm("tint")


def draw(points, rgb):
    # Tapered camera-facing ribbon with per-vertex brightness along the trail.
    previous = None
    for index, raw in enumerate(points):
        center = hou.Vector3(raw)
        delta = hou.Vector3(points[min(index+1, len(points)-1)]) - hou.Vector3(points[max(index-1, 0)])
        side = hou.Vector3((-delta[1], delta[0], 0))
        if side.length() < .00001:
            side = hou.Vector3((1, 0, 0))
        weight = (index + 1) / len(points)
        side = side.normalized() * (.006 + .017*weight)
        pair = []
        for sign in (-1, 1):
            pt = geo.createPoint()
            pt.setPosition(center + side*sign)
            pt.setAttribValue(color, tuple(c*(.18 + weight*.82) for c in rgb))
            pair.append(pt)
        if previous:
            quad = geo.createPolygon()
            for point in (previous[0], previous[1], pair[1], pair[0]):
                quad.addVertex(point)
        previous = pair


def pos(d, t):
    radius = speed * (1.0 - math.exp(-drag * t)) / drag
    return hou.Vector3((d[0]*radius, 1.1 + d[1]*radius - gravity*t*t/2, d[2]*radius))


if age < 0:
    height = 1.1 + age*4.2
    draw([(0, height - 0.7, 0), (0, height, 0)], (1.0, 0.75, 0.30))
else:
    for i, direction in enumerate(directions):
        flicker = 0.72 + 0.28 * ((i * 13) % 17) / 16
        rgb = (flicker, flicker*(0.36 + 0.56*tint), 0.16 + 0.50*tint)
        times = [max(0.0, age - trail*(1-j/6)) for j in range(7)]
        draw([pos(direction, t) for t in times], rgb)
        if delay > 0 and age > delay and i % 4 == 0:
            origin = pos(direction, delay)
            for sign in (-1, 1):
                side = hou.Vector3((direction[1]*sign, 0.55, -direction[0]*sign))
                def branch(t):
                    return origin + (direction + side)*t*1.6 + hou.Vector3((0, -gravity*t*t/2, 0))
                draw([branch(max(0, t-delay)) for t in times], (1.0, 0.4, 0.16))
