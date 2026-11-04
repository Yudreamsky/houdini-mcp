"""Success-only undo records for writes in the visible Houdini window."""
import tempfile
from pathlib import Path

import hou


def add(change, label):
    with hou.undos.group(label):
        hou.undos.add(change, label)


class ControlChange:
    def __init__(self, before, after, old_frame, new_frame):
        self.before, self.after = before, after
        self.old_frame, self.new_frame = old_frame, new_frame

    def apply(self, values, frame):
        with hou.undos.disabler():
            for path, value in values.items():
                hou.parm(path).set(value, follow_parm_reference=False)
            if self.old_frame != self.new_frame:
                hou.setFrame(frame)

    def undo(self):
        self.apply(self.before, self.old_frame)

    def redo(self):
        self.apply(self.after, self.new_frame)


def controls(label, action, parms):
    before = {parm.path(): parm.eval() for parm in parms}
    old_frame = hou.frame()
    with hou.undos.disabler():
        try:
            result = action()
            after = {p: hou.parm(p).eval() for p in before}
        except Exception:
            for path, value in before.items():
                if hou.parm(path).eval() != value:
                    hou.parm(path).set(value, follow_parm_reference=False)
            if hou.frame() != old_frame:
                hou.setFrame(old_frame)
            raise
    new_frame = hou.frame()
    if before != after or old_frame != new_frame:
        add(ControlChange(before, after, old_frame, new_frame), label)
    return result


GUIDES = (hou.viewportGuide.XZPlane, hou.viewportGuide.OriginGnomon, hou.viewportGuide.FloatingGnomon)


def scene_pose():
    pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    cam = pane.curViewport().camera() if pane else None
    return dict(active=getattr(hou.session, "hr_active_path", None), frame=hou.frame(),
                fps=hou.fps(), frames=tuple(hou.playbar.frameRange()), playback=tuple(hou.playbar.playbackRange()),
                camera=cam.path() if cam else None,
                plane=pane.constructionPlane().isVisible() if pane else None,
                guides=tuple(pane.curViewport().settings().guideEnabled(g) for g in GUIDES) if pane else ())


def restore_pose(pose, other):
    for key, setter in (("fps", hou.setFps), ("frames", lambda r: hou.playbar.setFrameRange(*r)),
                        ("playback", lambda r: hou.playbar.setPlaybackRange(*r)), ("frame", hou.setFrame)):
        if pose[key] != other[key]:
            setter(pose[key])
    hou.session.hr_active_path = pose["active"]
    pane = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if pane:
        if pose["camera"] != other["camera"]:
            pane.curViewport().setCamera(hou.node(pose["camera"]) if pose["camera"] else None)
        if pose["plane"] != other["plane"] and pose["plane"] is not None:
            pane.constructionPlane().setIsVisible(pose["plane"])
        if pose["guides"] != other["guides"]:
            for guide, enabled in zip(GUIDES, pose["guides"]):
                pane.curViewport().settings().enableGuide(guide, enabled)


class AddedObjects:
    """Keep native CPIO bytes in the undo stack so redo does not depend on a library file."""
    def __init__(self, created, before, after, old, visible):
        self.paths = tuple(n.path() for n in created)
        self.before, self.after = before, after
        self.old = old.path() if old else None
        self.visibility = (visible, old.isDisplayFlagSet() if old else None)
        with tempfile.TemporaryDirectory(prefix="houdini-undo-") as temp:
            file = Path(temp)/"nodes.cpio"
            hou.node("/obj").saveItemsToFile(tuple(created), str(file))
            self.archive = file.read_bytes()

    def undo(self):
        with hou.undos.disabler():
            for path in self.paths:
                node = hou.node(path)
                if node:
                    node.destroy()
            if self.old and self.visibility[0] != self.visibility[1]:
                hou.node(self.old).setDisplayFlag(self.visibility[0])
            restore_pose(self.before, self.after)

    def redo(self):
        with hou.undos.disabler(), tempfile.TemporaryDirectory(prefix="houdini-redo-") as temp:
            if any(hou.node(path) for path in self.paths):
                raise RuntimeError("Cannot redo: a restored object path is already occupied")
            file = Path(temp)/"nodes.cpio"
            file.write_bytes(self.archive)
            hou.node("/obj").loadItemsFromFile(str(file))
            if self.old and self.visibility[0] != self.visibility[1]:
                hou.node(self.old).setDisplayFlag(self.visibility[1])
            restore_pose(self.after, self.before)


def object_creation(label, action):
    obj = hou.node("/obj")
    originals = set(obj.children())
    before = scene_pose()
    old = hou.node(before["active"] or "/obj/HoudiniResearch")
    visible = old.isDisplayFlagSet() if old else None
    with hou.undos.disabler():
        try:
            result = action()
            created = [n for n in obj.children() if n not in originals]
            change = AddedObjects(created, before, scene_pose(), old, visible) if created else None
        except Exception:
            failed = scene_pose()
            for node in set(obj.children()) - originals:
                node.destroy()
            if old:
                old.setDisplayFlag(visible)
            restore_pose(before, failed)
            raise
    if change is not None:
        add(change, label)
    return result
