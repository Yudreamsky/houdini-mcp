"""Run with hython -m tests.rig_native to test native FK pivots and local axes."""
import tempfile
from pathlib import Path

import hou
from hlab.rig_worker import build


def verify():
    assert not hou.isUIAvailable()
    obj = hou.node("/obj")
    network = obj.createNode("subnet", "mechanism")
    network.parm("tz").set(-2)
    specs = []
    for name, x in [("arm", 2), ("carriage", 5), ("tip", 6)]:
        part = network.createNode("geo", name)
        part.createNode("box").setDisplayFlag(True)
        part.parmTuple("t").set((x, 0, 2))
        specs.append(dict(part=part.path(), pivot=[x, 0, 0], axis="z", kind="fixed", keys=[], limits=None,
                          parent=specs[-1]["part"] if specs else ""))
    specs[0].update(kind="hinge", pivot=[1, 0, 0], limits=[0, 90], keys=[(1, 0), (11, 90)])
    specs[1].update(kind="slider", axis="x", limits=[0, 2], keys=[(1, 0), (11, 2)])
    with tempfile.TemporaryDirectory() as folder:
        report = build(dict(joints=specs, frame=1, replace_motion=False, file=str(Path(folder)/"result.hip")))
        assert report["verified_after_reopen"]
        hou.setFrame(11)
        for j, expected in zip(specs, [(1, 1, 0), (1, 6, 0), (1, 7, 0)]):
            pos = hou.node(j["part"]).origin()
            assert (pos - hou.Vector3(expected)).length() < 1e-5, (j["part"], tuple(pos), expected)
    print("Verified off-centre 90-degree hinge, inherited slider axis and third-level fixed offset.")


if __name__ == "__main__":
    verify()
