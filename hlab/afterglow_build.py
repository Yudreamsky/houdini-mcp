"""Build the native two-burst HIP, then bake the first-burst-only Pyro cache."""
import argparse
import hashlib
import json
from pathlib import Path

import hou

HERE = Path(__file__).parent
END = 79


def build(folder,reuse_cache=False):
    obj = hou.node("/obj")
    controls = obj.createNode("null","DIRECTION")
    for key,label,value,upper in (("smoke","Smoke density",1.,4.),("flash","Light on old smoke",1.,3.),
                                 ("duration","Relight duration (frames)",7.,20.)):
        controls.addSpareParmTuple(hou.FloatParmTemplate(key,label,1,default_value=(value,),min=0,max=upper))
    controls.setDisplayFlag(False)
    geo = obj.createNode("geo","WILLOW_AND_BURST",run_init_scripts=False)
    sphere = geo.createNode("sphere","Shell")
    sphere.parm("type").set("polymesh")
    scatter = geo.createNode("scatter::2.0","Locked_Willow_Seed")
    scatter.setInput(0,sphere)
    scatter.setParms({"forcetotal":1,"npts":96,"seed":17})
    code = (HERE/"afterglow_sparks.vfl").read_text()
    merge = geo.createNode("merge","Two_bursts")
    for i, name in enumerate(("Willow","Second_Burst")):
        node=geo.createNode("attribwrangle",name)
        node.setInput(0,scatter)
        node.addSpareParmTuple(hou.IntParmTemplate("burst","Burst index",1,default_value=(i,)))
        node.parm("snippet").set(code)
        merge.setInput(i,node)
    merge.setDisplayFlag(True)
    merge.setRenderFlag(True)
    geo.layoutChildren()
    mat=hou.node("/mat").createNode("materialbuilder","Embers")
    bind=mat.createNode("bind","Particle_radiance")
    bind.setParms({"parmname":"Cd","parmtype":"color"})
    mat.node("surface_output").setInput(0,bind)
    mat.layoutChildren()
    geo.parm("shop_materialpath").set(mat.path())
    smoke=obj.createNode("geo","RESIDUAL_SMOKE",run_init_scripts=False)
    reference=smoke.createNode("object_merge","Willow_directions")
    reference.parm("objpath1").set(scatter.path())
    emit=smoke.createNode("attribwrangle","First_burst_only")
    emit.setInput(0,reference)
    emit.parm("snippet").set((HERE/"afterglow_source.vfl").read_text())
    raster=smoke.createNode("volumerasterizeattributes","Source_fields")
    raster.setInput(0,emit)
    raster.setParms({"attributes":"density temperature v","voxelsize":.075})
    solver=smoke.createNode("pyrosolver","Advect_and_dissipate")
    solver.setInput(0,raster)
    solver.setParms({"divsize":.075,"enable_wind":1,"wind_strength":1.45,"wind_directionx":1,
                     "enable_disturbance":1,"disturbance":.48,"disturbance_blocksize":.32,
                     "enable_turbulence":1,"turbulence":.48,"turbulence_swirlsize":.55,
                     "turbulence_usecontrol":0,"dissipation":.014,"buoyancylift":.018,"timescale":.72,"cachemaxsize":700})
    density=smoke.createNode("blast","Keep_density")
    density.setInput(0,solver)
    density.setParms({"group":"@name=density","negate":1})
    disk=smoke.createNode("file","First_burst_cache")
    disk.parm("file").set("$HIP/cache/smoke.$F4.bgeo.sc")
    disk.setDisplayFlag(True)
    disk.setRenderFlag(True)
    smoke.layoutChildren()
    shader=hou.node("/mat").createNode("pyroshader","Cold_smoke")
    shader.setParms({"fi_enable":0,"s_colorr":.66,"s_colorg":.68,"s_colorb":.72})
    shader.parm("s_densityscale").setExpression('ch("/obj/DIRECTION/smoke")*.14')
    smoke.parm("shop_materialpath").set(shader.path())
    cam=obj.createNode("cam","CAM")
    cam.parmTuple("t").set((-.28,.28,14.8))
    cam.setParms({"focal":41,"resx":768,"resy":432})
    cam.setDisplayFlag(False)
    for name,xyz,rgb,brightness in (
        ("Night_fill",(-3,5,6),(.24,.33,.56),".32"),
        ("First_ignition",(-1.35,.68,.38),(1,.54,.23),"if($FF>=11,6*exp(-max(0,$FF-11)/5),0)"),
        ("Second_flash",(.48,.95,.65),(1,.44,.19),'if($FF>=49,2.7*ch("/obj/DIRECTION/flash")*exp(-max(0,$FF-49)/2),0)')):
        light=obj.createNode("hlight",name)
        light.parmTuple("t").set(xyz)
        light.parmTuple("light_color").set(rgb)
        light.parm("light_intensity").setExpression(brightness)
    second_path=geo.node("Second_Burst").path()
    for slot in range(4):
        light=obj.createNode("hlight",f"Ember_{slot+1}")
        light.parmTuple("light_color").set((1,.46,.21))
        for axis,p in enumerate(light.parmTuple("t")):
            p.setExpression(f'detail("{second_path}","tip{slot}",{axis})')
        power=f'detail("{second_path}","power{slot}",0)'
        light.parm("light_intensity").setExpression(f'.92*{power}*ch("/obj/DIRECTION/flash")*exp(-max(0,$FF-49)/max(.1,ch("/obj/DIRECTION/duration")))')
    out=hou.node("/out").createNode("ifd","RELIGHT")
    out.setParms({"camera":cam.path(),"vobject":"WILLOW_AND_BURST RESIDUAL_SMOKE","vm_picture":"$HIP/render/$F4.exr",
                  "vm_samplesx":3,"vm_samplesy":3,"vm_maxraysamples":4,"vm_volumesteprate":.5,"soho_foreground":1})
    obj.layoutChildren()
    hou.setFps(24)
    hou.playbar.setFrameRange(1,END)
    hou.playbar.setPlaybackRange(1,END)
    if reuse_cache:
        if not (folder/"cache.json").is_file() or len(list((folder/"cache").glob("smoke.*.bgeo.sc")))!=END:
            raise RuntimeError("No complete first-burst cache to reuse")
        hou.setFrame(53)
        hou.hipFile.save(str(folder/"Afterglow.hip"))
        return
    hou.setFrame(1)
    hou.hipFile.save(str(folder/"Afterglow.hip"))
    (folder/"cache").mkdir(exist_ok=True)
    digest=hashlib.sha256()
    sizes=[]
    for frame in range(1,END+1):
        hou.setFrame(frame)
        vol=density.geometry()
        if density.errors() or solver.errors() or emit.errors():
            raise RuntimeError((density.errors(),solver.errors(),emit.errors()))
        f=folder/"cache"/f"smoke.{frame:04d}.bgeo.sc"
        vol.saveToFile(str(f))
        digest.update(f.read_bytes())
        sizes.append(f.stat().st_size)
        if frame%10==0:
            print("Pyro cache",frame,sizes[-1],flush=True)
    hou.setFrame(52)
    fireworks = merge.geometry()
    if not fireworks or not fireworks.prims():
        raise RuntimeError(f"Sparks failed: {merge.errors()}")
    hou.hipFile.save(str(folder/"Afterglow.hip"))
    (folder/"cache.json").write_text(json.dumps({"frames":END,"sha256":digest.hexdigest(),"bytes":sum(sizes),"version":hou.applicationVersionString()},indent=2))
    print("Baked",folder,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("--reuse-cache",action="store_true")
    args=parser.parse_args()
    folder=args.folder.resolve()
    folder.mkdir(parents=True,exist_ok=True)
    build(folder,args.reuse_cache)
