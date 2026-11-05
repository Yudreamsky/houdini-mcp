"""hython -m tests.window_save_native: window_save writes the scene's own HIP or a new path, never another file."""
import hashlib
import tempfile
from pathlib import Path

import hou

from hlab import scene
from hlab.storage import example


def denied(action, fragment):
    try:
        action()
    except ValueError as exc:
        assert fragment in str(exc), exc
    else:
        raise AssertionError("Unexpectedly accepted: " + fragment)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(folder):
    suffix = scene.HIP_SUFFIX.get(hou.licenseCategory().name(), ".hipnc")
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.node("/obj").createNode("geo", "FIRST")
    denied(lambda: scene.window_save(), "never been saved")
    first, second, other = (folder / (name + suffix) for name in ("first", "second", "other"))
    saved = scene.window_save(str(first))
    assert saved["status"] == "saved" and Path(saved["hip"]) == first, saved
    assert saved["bytes"] == first.stat().st_size and saved["sha256"] == digest(first)
    other.write_bytes(b"keep")
    hou.node("/obj").createNode("geo", "SECOND")
    denied(lambda: scene.window_save(str(other)), "Another file exists")
    denied(lambda: scene.window_save("relative" + suffix), "absolute path")
    denied(lambda: scene.window_save(str(folder / "wrong.hipx")), "ending in " + suffix)
    denied(lambda: scene.window_save(str(folder / "missing" / ("x" + suffix))), "Missing folder")
    denied(lambda: scene.window_save(str(example().parents[1] / ("copy" + suffix))), "Bundled examples")
    assert other.read_bytes() == b"keep" and not (folder / "missing").exists()
    # The window's own file, by default or under another spelling of its path, is saved in place.
    before = digest(first)
    assert scene.window_save()["sha256"] == digest(first) != before
    hou.node("/obj").createNode("geo", "THIRD")
    in_place = scene.window_save(str(first).replace("/", "\\").upper())
    assert Path(in_place["hip"]) == first and in_place["sha256"] == digest(first)
    kept = digest(first)
    moved = scene.window_save(str(second))
    assert Path(moved["hip"]) == second and Path(hou.hipFile.path()) == second and digest(first) == kept
    denied(lambda: scene.window_save(str(first)), "Another file exists")
    hou.hipFile.load(str(first), suppress_save_prompt=True)
    assert [n.name() for n in hou.node("/obj").children()] == ["FIRST", "SECOND", "THIRD"]
    sample = example("rain").parent / "Rain.hip"
    hou.hipFile.load(str(sample), suppress_save_prompt=True, ignore_load_warnings=True)
    before = digest(sample)
    denied(lambda: scene.window_save(), "Bundled examples")
    assert digest(sample) == before
    print("PASS save as, in place under any spelling, refused overwrites, bad paths and bundled examples")


if __name__ == "__main__":
    assert not hou.isUIAvailable()
    with tempfile.TemporaryDirectory() as tmp:
        check(Path(tmp).resolve())
