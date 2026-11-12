"""Run python -m tests.karma_cutout_native for real Karma renders of cut-out cards. On XPU a Principled opacity
texture, or the alpha of its base colour texture, converts to MaterialX, so the cut-away part is a hole as on CPU:
transparent in the picture, and still a hole through twelve stacked cards."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Picture columns (of 900) of each stack's cut-away half and kept half; see fixture() for the layout.
SPOTS = {"one over wall": (203, 252), "twelve over wall": (351, 401), "alpha over nothing": (549, 598)}


def fixture(folder):
    """Three stacks of cards whose left half is cut away: one card and twelve cards with an opacity texture in front
    of a red glowing wall, and one card cut by its base colour texture's alpha with nothing behind it. The blue sky
    lights the scene but is hidden from the camera."""
    import hou
    hou.hipFile.clear(suppress_save_prompt=True)
    obj, mat = hou.node("/obj"), hou.node("/mat")

    def texture(name):
        return (folder / name).as_posix()

    glow = mat.createNode("principledshader::2.0", "red_glow")
    glow.parmTuple("basecolor").set((0, 0, 0))
    glow.parmTuple("emitcolor").set((1, 0, 0))
    glow.parm("emitint").set(1)
    wall = obj.createNode("geo", "WALL")
    grid = wall.createNode("grid")
    grid.parm("orient").set(0)
    grid.parmTuple("size").set((4.4, 6))
    grid.parmTuple("t").set((-1.6, 0, -3))
    grid.setDisplayFlag(True)
    grid.setRenderFlag(True)
    wall.parm("shop_materialpath").set(glow.path())
    leaf = mat.createNode("principledshader::2.0", "leaf")
    leaf.parmTuple("basecolor").set((1, 1, 1))
    leaf.setParms({"basecolor_useTexture": 1, "basecolor_texture": texture("green.png"),
                   "opaccolor_useTexture": 1, "opaccolor_texture": texture("half.png")})
    alpha = mat.createNode("principledshader::2.0", "leaf_alpha")
    alpha.parmTuple("basecolor").set((1, 1, 1))
    alpha.setParms({"basecolor_useTexture": 1, "basecolor_texture": texture("green_alpha.png"),
                    "basecolor_useTextureAlpha": 1})
    for name, layers, x, material in (("ONE", 1, -2., leaf), ("TWELVE", 12, -.5, leaf), ("ALPHA", 1, 1.5, alpha)):
        geo = obj.createNode("geo", name)
        card = geo.createNode("grid")
        card.parm("orient").set(0)
        card.parmTuple("size").set((1, 1))
        uv = geo.createNode("attribwrangle")
        uv.setInput(0, card)
        uv.parm("snippet").set("v@uv = relbbox(0, @P);")
        stack = geo.createNode("copyxform")
        stack.setInput(0, uv)
        stack.parm("ncy").set(layers)
        stack.parmTuple("t").set((0, 0, -.1))
        move = geo.createNode("xform")
        move.setInput(0, stack)
        move.parmTuple("t").set((x, 0, 0))
        assign = geo.createNode("material")  # per-primitive, as foliage tools assign leaf materials
        assign.setInput(0, move)
        assign.parm("shop_materialpath1").set(material.path())
        assign.setDisplayFlag(True)
        assign.setRenderFlag(True)
    sky = obj.createNode("envlight", "SKY")
    sky.parmTuple("light_color").set((.2, .4, 1))
    cam = obj.createNode("cam", "CAM")
    cam.parmTuple("t").set((.25, 0, 11))
    cam.setParms({"resx": 900, "resy": 220, "focal": 50})
    hou.setFrame(1)
    hou.hipFile.save(str(folder / "cutout.hip"), save_to_recent_files=False)


def spot(picture, column):
    """Mean RGBA of a 9 x 9 box at mid height."""
    box = picture.crop((column - 4, picture.height // 2 - 4, column + 5, picture.height // 2 + 5))
    data = box.tobytes()
    return tuple(sum(data[i::4]) / (len(data) // 4) for i in range(4))


def accept(directory):
    from PIL import Image
    from hlab import karma
    from hlab.runtime import discover
    from hlab.storage import sha
    from hlab.worker_pool import pool

    Image.new("RGB", (64, 64), (40, 200, 60)).save(directory / "green.png")
    half = Image.new("L", (64, 64), 0)
    half.paste(255, (32, 0, 64, 64))
    half.save(directory / "half.png")
    rgba = Image.new("RGBA", (64, 64), (40, 200, 60, 0))
    rgba.paste((40, 200, 60, 255), (32, 0, 64, 64))
    rgba.save(directory / "green_alpha.png")
    subprocess.run([str(discover().hython), "-m", "tests.karma_cutout_native", str(directory)], check=True,
                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL)
    hip = directory / "cutout.hip"
    before = sha(hip)

    report = karma.inspect(str(hip))["material_conversion"]
    assert {r["source"] for r in report["xpu"]["converted"]} == {"/mat/leaf", "/mat/leaf_alpha"}, report["xpu"]
    assert report["cpu"]["converted"] == [], report["cpu"]  # CPU runs the Principled shader itself

    seen = {}
    for label, changes in (("xpu", {"engine": "xpu"}), ("cpu", {"engine": "cpu"}),
                           ("xpu as authored", {"engine": "xpu", "convert_materials": False})):
        run, _ = karma.render(str(hip), "/obj/CAM", 1, "preview", {**changes, "samples": 64, "width": 900})
        assert run["status"] == "completed" and run["hip_unchanged"], run["notes"]
        with Image.open(run["path"]) as picture:
            rgba = picture.convert("RGBA")
        seen[label] = {name: (spot(rgba, hole), spot(rgba, kept)) for name, (hole, kept) in SPOTS.items()}
        if label == "xpu":
            assert {c["source"] for c in run["materials"]["converted"]} == {"/mat/leaf", "/mat/leaf_alpha"}, run["materials"]
            assert "镂空" in " ".join(n for c in run["materials"]["converted"] for n in c["notes"]), run["materials"]
    for label in ("xpu", "cpu"):
        for name in ("one over wall", "twelve over wall"):
            hole, kept = seen[label][name]
            assert hole[0] > 200 and hole[1] < 100 and hole[2] < 100, (label, name, "the wall should show through", hole)
            assert kept[1] > kept[0] + 40 and kept[1] > kept[2] + 40 and kept[3] > 250, (label, name, kept)
        hole, kept = seen[label]["alpha over nothing"]
        assert hole[3] < 5, (label, "a hole with nothing behind is transparent in the picture", hole)
        assert kept[1] > kept[0] + 40 and kept[3] > 250, (label, kept)
    # XPU's own approximation, for the record: the stack goes dark and the hole stays opaque in the picture.
    authored = seen["xpu as authored"]
    still_needed = authored["twelve over wall"][0][0] < 100 or authored["alpha over nothing"][0][3] > 250
    assert sha(hip) == before
    pool.close()
    print("PASS cut-outs on XPU match CPU: the wall shows through 1 and 12 cards, texture alpha cuts a real hole;",
          "XPU's own Principled approximation", "still loses them" if still_needed else "now renders them too",
          {k: [round(c) for c in v[0]] for k, v in authored.items()})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fixture(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="karma-cutout-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp, "HOUDINI_RESEARCH_WORKER": "warm"}):
                accept(Path(tmp))
