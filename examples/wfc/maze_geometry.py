"""Embedded Python SOP source: make shared maze walls from the WFC passage layout."""

import json
import hou


def build():
    node = hou.pwd()
    control = node.parent()
    result = json.loads(node.inputs()[0].geometry().stringAttribValue("wfc_result"))
    layout = result["layout"]
    pitch = control.evalParm("pitch")
    height = control.evalParm("wall_height")
    thickness = control.evalParm("wall_thickness")
    if pitch <= 0 or height <= 0 or not 0 < thickness < pitch:
        raise ValueError("Use positive dimensions and wall_thickness smaller than pitch")
    geometry = node.geometry()
    geometry.clear()
    geometry.addAttrib(hou.attribType.Prim, "part", "")
    geometry.addAttrib(hou.attribType.Prim, "cell", (-1, -1))
    geometry.addAttrib(hou.attribType.Prim, "Cd", (1., 1., 1.))

    def box(center, size, part, cell, color):
        points = geometry.createPoints([
            tuple(center[i] + sign[i] * size[i] / 2 for i in range(3))
            for sign in ((-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1),
                         (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1))])
        for face in ((0,3,2,1), (4,5,6,7), (0,1,5,4), (3,7,6,2), (0,4,7,3), (1,2,6,5)):
            polygon = geometry.createPolygon()
            for index in face:
                polygon.addVertex(points[index])
            polygon.setAttribValue("part", part)
            polygon.setAttribValue("cell", cell)
            polygon.setAttribValue("Cd", color)

    rows, columns = len(layout), len(layout[0])
    box((columns*pitch/2, -.10, -rows*pitch/2), (columns*pitch, .20, rows*pitch),
        "floor", (-1, -1), (.12, .19, .20))
    count = 0
    for y, row in enumerate(layout):
        for x, tile in enumerate(row):
            # Each shared wall is emitted once. The two exterior gates stay open.
            walls = []
            if "E" not in tile:
                walls.append(((x+1)*pitch, -(y+.5)*pitch, thickness, pitch))
            if "N" not in tile:
                walls.append(((x+.5)*pitch, -(y+1)*pitch, pitch, thickness))
            if x == 0 and "W" not in tile:
                walls.append((0, -(y+.5)*pitch, thickness, pitch))
            if y == 0 and "S" not in tile:
                walls.append(((x+.5)*pitch, 0, pitch, thickness))
            for px, pz, sx, sz in walls:
                box((px, height/2, pz), (sx, height, sz), "wall", (x, y), (.61, .76, .73))
                count += 1
    geometry.addAttrib(hou.attribType.Global, "wfc_result", "")
    geometry.setGlobalAttribValue("wfc_result", json.dumps(result))
    geometry.addAttrib(hou.attribType.Global, "wall_segments", count)


build()
