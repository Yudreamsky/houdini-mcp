"""A Houdini diagnostic for the descent law, separate from the approved fireworks shot."""
import json
import math
from pathlib import Path

import hou


def scene(path):
    g=hou.node("/obj").createNode("geo","EMBER_MOTION",run_init_scripts=False)
    seed=g.createNode("add","Seed")
    for legacy in (True,False):
        name="Legacy_gravity" if legacy else "Drag_on_whole_velocity"
        n=g.createNode("attribwrangle",name)
        n.setInput(0,seed)
        n.parm("class").set(0)
        for key,value in (("drag",1.15),("gravity",2.9),("wind_x",0.)):
            n.addSpareParmTuple(hou.FloatParmTemplate(key,key,1,default_value=(value,)))
        code="""
        float k=max(.001,chf("drag")), g=chf("gravity");
        vector wind=set(chf("wind_x"),0,0);
        vector v0=set(4.2,0,0), gravity=set(0,-g,0);
        float age=(@Frame-1)/24.0;
        int line=addprim(0,"polyline");
        for(int i=0;i<=32;i++){
            float t=age*i/32.0, e=exp(-k*t);
            vector vt=wind+gravity/k;
            vector pos=vt*t+(v0-vt)*(1-e)/k;
            vector vel=vt+(v0-vt)*e;
            LEGACY
            int pt=addpoint(0,pos);addvertex(0,line,pt);
            setpointattrib(0,"v",pt,vel,"set");
            setpointattrib(0,"Cd",pt,COLOUR,"set");
            if(i==32){setdetailattrib(0,"head_v",vel,"set");}
        }
        """
        old="pos=wind*t+(v0-wind)*(1-e)/k+gravity*t*t*.5;vel=wind+(v0-wind)*e+gravity*t;"
        n.parm("snippet").set(code.replace("LEGACY",old if legacy else "").replace("COLOUR","set(.8,.35,.1)" if legacy else "set(.1,.65,.95)"))
    merge=g.createNode("merge","COMPARE")
    a=g.node("Legacy_gravity")
    b=g.node("Drag_on_whole_velocity")
    merge.setInput(0,a);merge.setInput(1,b)
    merge.setDisplayFlag(True);merge.setRenderFlag(True);g.layoutChildren()
    hou.setFps(24);hou.playbar.setFrameRange(1,145);hou.playbar.setPlaybackRange(1,145)
    rows=[]
    for f in (1,13,25,73,145):
        hou.setFrame(f)
        gv=b.geometry().attribValue("head_v");age=(f-1)/24
        old_v=a.geometry().attribValue("head_v")
        assert abs(gv[1]+2.9/1.15*(1-math.exp(-1.15*age)))<2e-5
        rows.append({"t":age,"vx":gv[0],"vy":gv[1],"legacy_vy":old_v[1]})
    assert abs(rows[-1]["vy"]+2.9/1.15)<.003
    hou.setFrame(73);hou.hipFile.save(str(path))
    return {"model":"linear drag on velocity relative to air, constant mass, still air",
            "launch_v":[4.2,0,0],"g":2.9,"drag_per_second":1.15,"terminal_vy":-2.9/1.15,"samples":rows}


if __name__=="__main__":
    out=Path(__file__).resolve().parent
    facts=scene(out/"Ember-drag-study.hip")
    (out/"observations.json").write_text(json.dumps(facts,indent=2),encoding="utf8")
