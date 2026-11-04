"""Run in hython against a baked Afterglow.hip to check the physical A/B controls."""
import hashlib
import json
import sys
from pathlib import Path

import hou


def fingerprint(node):
    geo = node.geometry()
    if not geo.intrinsicValue("pointcount"):
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(geo.pointFloatAttribValuesAsString("P") + geo.pointFloatAttribValuesAsString("Cd")).hexdigest()


def check(folder):
    hou.hipFile.load(str(folder/"Afterglow.hip"),suppress_save_prompt=True)
    knobs = hou.node("/obj/DIRECTION")
    willow = hou.node("/obj/WILLOW_AND_BURST/Willow")
    stars = hou.node("/obj/WILLOW_AND_BURST/Second_Burst")
    smoke = hou.node("/obj/RESIDUAL_SMOKE/First_burst_cache")
    lights = [hou.node(f"/obj/Ember_{i}") for i in range(1,5)]
    result = {}
    for frame in (48,53,61):
        hou.setFrame(frame)
        knobs.setParms({"smoke":1,"flash":1,"duration":7})
        initial = [fingerprint(n) for n in (willow,stars)]
        source = Path(smoke.evalParm("file"))
        grid = hashlib.sha256(source.read_bytes()).hexdigest()
        positions = [list(light.parmTuple("t").eval()) for light in lights]
        power = [l.evalParm("light_intensity") for l in lights]
        if frame>=49:
            geometry = stars.geometry()
            for i, pos in enumerate(positions):
                assert tuple(pos)==geometry.attribValue(f"tip{i}")
            assert max(power)>0
        else:
            assert not any(power)
        knobs.setParms({"smoke":.60,"flash":.85,"duration":4})
        knobs.parm("smoke").set(1)
        assert [fingerprint(n) for n in (willow,stars)]==initial
        assert Path(smoke.evalParm("file"))==source
        knobs.parm("flash").set(0)
        assert not any(l.evalParm("light_intensity") for l in lights)
        assert hou.node("/obj/Second_flash").evalParm("light_intensity")==0
        assert [fingerprint(n) for n in (willow,stars)]==initial
        result[frame]={"willow_sha":initial[0],"sparks_sha":initial[1],"density_file_sha":grid,"tip_xyz":positions,"tip_power":power}
    assert result[53]["tip_xyz"]!=result[61]["tip_xyz"]
    return result


if __name__=="__main__":
    print(json.dumps(check(Path(sys.argv[1]).resolve()),indent=2))
