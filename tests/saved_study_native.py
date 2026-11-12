"""Run python -m tests.saved_study_native for saved HIP comparisons, motion and optical evidence."""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def fixture(path):
    import hou
    assert not hou.isUIAvailable()
    obj = hou.node("/obj")
    mesh = obj.createNode("geo", "mesh", run_init_scripts=False)
    box = mesh.createNode("box", "box")
    box.parm("tx").setExpression("$FF * 0.1", hou.exprLanguage.Hscript)
    mesh.createNode("box", "static_witness")
    box.setDisplayFlag(True)
    box.setRenderFlag(True)
    cam = obj.createNode("cam", "cam")
    cam.parm("tz").set(6)
    cam.parm("resx").set(80)
    cam.parm("resy").set(64)
    light = obj.createNode("hlight")
    light.parmTuple("t").set((1, 2, 4))
    out = hou.node("/out").createNode("ifd", "optics")
    out.parm("camera").set(cam.path())
    hou.hipFile.save(str(path), save_to_recent_files=False)


def accept(directory):
    from PIL import Image
    from hlab.runtime import discover
    from hlab.sop_lab import study_saved
    from hlab.storage import details, sha, stored
    from hlab.worker_pool import pool

    file = directory/"saved.hip"
    subprocess.run([str(discover().hython), str(Path(__file__).resolve()), str(file)], check=True, timeout=180)
    before = sha(file)
    node = "/obj/mesh/box"
    comp = study_saved(str(file), "compare", node, variants={"wide":{"sizex":2}, "tall":{"sizey":2}},
                       frame=4, witness="/obj/mesh/static_witness", renderer="/out/optics", camera="/obj/cam")
    assert comp["observed_change"] and comp["baseline_restored"] and comp["hip_sha256"] == before
    assert comp["observed_pixel_change"] and not comp["observed_geometry_change"]
    assert comp["process"] == "warm" and details(comp["id"])["details"]["process"] == "warm"
    images = []
    for candidate in comp["candidates"].values():
        sample = candidate["samples"][0]
        path = stored("images", sample["image_id"]+".png")
        assert sha(path) == sample["sha256"] and sample["renderer"] == "/out/optics"
        assert sample["camera"] == "/obj/cam" and sample["frame"] == 4
        with Image.open(path) as picture:
            assert picture.size == (80,64)
            assert any(lo != hi for lo,hi in picture.convert("RGB").getextrema())
            images.append(hashlib.sha256(picture.convert("RGBA").tobytes()).hexdigest())
            assert images[-1] == sample["pixel_sha256"]
    assert images[0] != images[1]
    motion = study_saved(str(file), "motion", node, frames=[2,4,7], changes={"sizey":2}, topic="saved-test")
    assert motion["observed_change"] and motion["baseline_restored"] and motion["process_pid"] == comp["process_pid"]
    assert motion["observed_geometry_change"] and motion["observed_pixel_change"] is None
    assert [round(s["metrics"]["bbox_min"][0],2) for s in motion["samples"]] == [-.30,-.10,.20]
    assert all("image_id" not in sample for sample in motion["samples"])
    try:
        study_saved(str(file), "motion", node, frames=[2,4], capture=True)
    except ValueError as exc:
        assert "Mantra or Karma ROP" in str(exc)
    else:
        raise AssertionError("An unspecified saved renderer was accepted")
    with patch.dict(os.environ, {"HOUDINI_RESEARCH_WORKER":"spawn"}):
        fresh = study_saved(str(file), "motion", node, frames=[2,4], topic="saved-test")
    assert fresh["process"] == "fresh" and details(fresh["id"])["details"]["process"] == "fresh"
    assert fresh["process_pid"] != motion["process_pid"] and sha(file) == before
    pool.close()
    print("PASS saved HIP bytes, multi-parameter compare, distinct 80x64 optical PNGs, motion, warm and fresh receipts")


if __name__=="__main__":
    if len(sys.argv) > 1:
        fixture(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="saved-study-acceptance-") as tmp:
            with patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME":tmp, "HOUDINI_RESEARCH_WORKER":"warm"}):
                accept(Path(tmp))
