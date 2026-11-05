"""Run python -m tests.karma_materials_native [output-dir] for native material regressions.

Uses a separate hython process and small CPU renders; never opens a GUI or saves
the converted scene. Passing an output directory retains the PNGs and fixtures.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(directory):
    import hou
    from hlab import karma_materials
    from hlab.karma_render import render

    settings = {"engine": "cpu", "samples": 1, "denoiser": "off", "max_edge": 64,
                "time_limit": 20, "motion_blur": False, "convert_materials": False}

    def camera():
        cam = hou.node("/obj").createNode("cam", "CAM")
        cam.parmTuple("t").set((0, 0, 4))
        cam.parm("resx").set(64)
        cam.parm("resy").set(64)

    def shot(name, convert=False):
        folder = directory / name
        folder.mkdir(exist_ok=True)
        result = render({"settings": {**settings, "convert_materials": convert},
                         "frame": 1, "camera": "/obj/CAM"}, folder)
        assert result["status"] == "completed", result
        assert (folder / "render.png").is_file(), result
        return result

    hou.hipFile.clear(suppress_save_prompt=True)
    material = hou.node("/mat").createNode("principledshader::2.0", "TRANSPARENT")
    material.parm("basecolor_useTexture").set(1)
    material.parm("basecolor_texture").set(str(directory / "white.png"))
    material.parmTuple("basecolor").set((1, 0, 0))
    material.parm("reflect").set(0)
    # The color is multiplied by the scalar, not substituted for it.
    material.parm("opac").set(.4)
    material.parmTuple("opaccolor").set((.25, .5, 1))
    tinted, _ = karma_materials.principled(material, karma_materials.Network(material))
    assert all(abs(a - b) < 1e-6 for a, b in zip(tinted.parmTuple("opacity").eval(), (.1, .2, .4))), \
        tinted.parmTuple("opacity").eval()
    material.parm("opac").set(1)
    material.parmTuple("opaccolor").set((0, 0, 0))
    # XPU converts a Principled only for features its own fallback drops; a flat bump map is one of them.
    material.parm("baseBumpAndNormal_enable").set(1)
    material.parm("baseBumpAndNormal_type").set("bump")
    material.parm("baseBump_bumpTexture").set(str(directory / "white.png"))
    geo = hou.node("/obj").createNode("geo", "BOX")
    box = geo.createNode("box")
    box.setDisplayFlag(True)
    box.setRenderFlag(True)
    geo.parm("shop_materialpath").set(material.path())
    camera()
    opacity_hip = directory / "opacity.hip"
    hou.hipFile.save(str(opacity_hip), save_to_recent_files=False)
    opacity_before = digest(opacity_hip)
    original = shot("opacity-original")
    # Exercise the XPU conversion path while using CPU for a deterministic,
    # inexpensive comparison of the original and resulting shader networks.
    converted = karma_materials.convert("xpu")
    target = hou.node(converted["converted"][0]["material"])
    assert target.parmTuple("opacity").eval() == (0, 0, 0)
    transparent = shot("opacity-converted")
    assert digest(opacity_hip) == opacity_before

    hou.hipFile.clear(suppress_save_prompt=True)
    flat = hou.node("/shop").createNode("v_constant", "FLAT")
    flat.parmTuple("clr").set((.1, .4, .9))
    asset = hou.node("/obj").createNode("subnet", "ASSET")
    inner = asset.createNode("subnet", "INNER")
    pieces = inner.createNode("geo", "PIECES")
    box = pieces.createNode("box")
    assigned = pieces.createNode("attribwrangle", "MATERIAL")
    assigned.setInput(0, box)
    assigned.parm("class").set(1)
    assigned.parm("snippet").set('s@shop_materialpath = "/shop/FLAT";')
    assigned.setDisplayFlag(True)
    assigned.setRenderFlag(True)
    inner_file = directory / "inner.hda"
    inner = inner.createDigitalAsset(name="hr_test_karma_inner", hda_file_name=str(inner_file))
    inner.matchCurrentDefinition()
    # Also cover an object-level assignment inside the locked outer asset.
    other = asset.createNode("geo", "OBJECT_ASSIGNED")
    other.parmTuple("t").set((1.5, 0, 0))
    other.parm("shop_materialpath").set(flat.path())
    other_box = other.createNode("box")
    other_box.setDisplayFlag(True)
    other_box.setRenderFlag(True)
    outer_file = directory / "outer.hda"
    asset = asset.createDigitalAsset(name="hr_test_karma_outer", hda_file_name=str(outer_file),
                                    ignore_external_references=True)
    asset.matchCurrentDefinition()
    camera()
    locked_hip = directory / "locked.hip"
    hou.hipFile.save(str(locked_hip), save_to_recent_files=False)
    files = [locked_hip, inner_file, outer_file]
    before = {str(path): digest(path) for path in files}
    hou.hipFile.load(str(locked_hip), suppress_save_prompt=True)
    assert hou.node("/obj/ASSET").isLockedHDA()
    assert hou.node("/obj/ASSET/INNER").isLockedHDA()
    locked = shot("locked-converted", convert=True)
    mapped = locked["materials"]["converted"][0]["material"]
    assert locked["materials"]["converted"][0]["objects"] == 2
    output = hou.node("/obj/ASSET/INNER/PIECES").renderNode()
    assert output.geometry().findPrimAttrib("shop_materialpath").strings() == (mapped,)
    assert hou.node("/obj/ASSET/OBJECT_ASSIGNED").evalParm("shop_materialpath") == mapped
    assert {str(path): digest(path) for path in files} == before
    # A fresh load must retain the original asset locks and material bindings.
    hou.hipFile.load(str(locked_hip), suppress_save_prompt=True)
    assert hou.node("/obj/ASSET").isLockedHDA()
    assert hou.node("/obj/ASSET/INNER").isLockedHDA()
    output = hou.node("/obj/ASSET/INNER/PIECES").renderNode()
    assert output.geometry().findPrimAttrib("shop_materialpath").strings() == ("/shop/FLAT",)
    assert hou.node("/obj/ASSET/OBJECT_ASSIGNED").evalParm("shop_materialpath") == "/shop/FLAT"
    result = {"opacity_original": original, "opacity_converted": transparent, "locked": locked,
              "source_files_unchanged": True}
    (directory / "native-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def accept(directory):
    from PIL import Image
    from hlab.runtime import discover

    directory.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (255, 255, 255)).save(directory / "white.png")
    subprocess.run([str(discover().hython), "-m", "tests.karma_materials_native", "--hython", str(directory)],
                   cwd=Path(__file__).resolve().parents[1], check=True, timeout=180)
    for label in ("opacity-original", "opacity-converted"):
        with Image.open(directory / label / "render.png") as picture:
            assert picture.size == (64, 64)
            assert picture.getchannel("A").getextrema() == (0, 0), label
    with Image.open(directory / "locked-converted" / "render.png") as picture:
        assert picture.size == (64, 64)
        assert picture.getpixel((32, 32))[3] == 255
        assert all(abs(a - b) <= 6 for a, b in zip(picture.getpixel((32, 32))[:3], (89, 170, 244)))
    print("PASS Principled opacity color/scalar, original/converted pixels, nested locked HDA render, "
          "primitive/object bindings and unchanged source HIP/HDA:", directory)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--hython":
        native(Path(sys.argv[2]).resolve())
    elif len(sys.argv) > 1:
        accept(Path(sys.argv[1]).resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="karma-materials-") as tmp:
            accept(Path(tmp))
