"""Build an editable macro rain study. Scene length unit is one centimetre."""
import argparse
import math
from pathlib import Path

import hou

# x, z, contact frame, dominant wavelength (cm), relative amplitude, random seed.
HITS = [(-1.1,.30,10,.54,1.,2),(.94,-.36,25,.43,.77,7),(-.12,1.36,43,.38,.60,11),
        (1.78,.86,59,.49,.84,19),(-1.68,-.91,72,.42,.64,23)]
FPS = 24
SLOW = .055

BANK = """
float r = distance(set(@P.x,0,@P.z), set(chf("cx"),0,chf("cz")));
float t = (@Frame - chi("impact")) / 24.0;
float w = max(.05, chf("lambda"));
float k = 2*M_PI/w;
float omega = sqrt(981*k+72*pow(k,3));
float vg = (981+216*k*k)/(2*omega) * .055;
float front = vg*t;
float packet = 1-smooth(.03,.25, r-front);
float wake = exp(-pow(max(0,front-r)/(.24 + .23*max(t,0)),2));
vector displaced = point(1,"P",@ptnum);
float raw = displaced.y;
float mask = chi("front") ? packet*wake : 1;
@P.y += t>=0 ? raw*mask*smooth(0,.06,t)*exp(-.40*t) : 0;
"""

# Analytic virtual environment seen in the reflected ray. Stored inside the HIP.
WATER_LOOK = """
vector v=normalize(chv("eye")-@P);
vector surf=normalize(v@N);
if(chi("detail")){
    float t=@Time*.10;
    surf=normalize(surf+set(.013*sin(@P.x*5.2+@P.z*1.4+t)+.007*sin(@P.z*10.1-t),0,.016*sin(@P.z*4.8+@P.x*2.2-t)));
}
vector R=reflect(-v,surf);
float fres=.0204+.9796*pow(1-max(0,dot(v,surf)),5);
float u=R.x/max(.15,abs(R.z)), h=R.y/max(.15,abs(R.z));
vector sky=lerp(set(.028,.075,.088),set(.42,.71,.73),smooth(.04,1.5,h));
float amber=exp(-pow((u-.24)/.16,2)-pow((h-.82)/.72,2));
float tall=exp(-pow((u+.56)/.055,2)-pow((h-.93)/.78,2));
float horizon=exp(-pow((h-.67)/.048,2));
sky+=set(4.2,1.9,.57)*amber+set(1.1,1.62,1.84)*tall+set(.12,.20,.21)*horizon;
if(chi("detail")){
    float bank=.44+.10*sin(u*8.2)+.035*sin(u*27);
    float rise=smooth(bank-.025,bank+.025,h);
    float dusk=.5+.5*tanh((h-.71)*4);
    sky=lerp(set(.022,.041,.039),sky,rise);
    float limb=u+.07*sin(h*6.3)+.022*sin(h*17);
    float branches=1-.74*exp(-pow((limb-.26)/.014,2))-.44*exp(-pow((limb-.19)/.011,2));
    sky*=lerp(1,branches,smooth(.38,.72,h));
    sky+=set(2.1,1.0,.27)*exp(-pow((u-.12)/.079,2)-pow((h-.69)/.10,2));
    sky+=set(.23,.41,.46)*exp(-pow((h-.84-.09*sin(7*u))/.036,2))*dusk;
}
float texture = .5+.5*noise(@P*1.9);
v@Cd=set(.011,.040,.044)*(.82+.28*texture)+fres*sky*chf("reflection");
"""


def parm(node,name,value,lo=0,hi=10):
    cls=hou.IntParmTemplate if type(value) is int else hou.FloatParmTemplate
    node.addSpareParmTuple(cls(name,name.replace("_"," ").title(),1,default_value=(value,),min=lo,max=hi))


def wrangle(parent,name,inputs,code):
    n=parent.createNode("attribwrangle",name)
    for i,upstream in enumerate(inputs):
        n.setInput(i,upstream)
    n.parm("snippet").set(code)
    return n


def build(path):
    obj=hou.node("/obj")
    water=obj.createNode("geo","RAIN",run_init_scripts=False)
    ctrl=water.createNode("null","ART_DIRECTION")
    for key,default in (("front",0),("stagger",0),("reflection",3.6),("amplitude",1.),("drop_detail",0),("look_detail",0)):
        parm(ctrl,key,default,0,8 if type(default) is float else 1)
    grid=water.createNode("grid","Undisturbed_water")
    grid.setParms({"sizex":13,"sizey":15,"rows":361,"cols":313})
    previous=grid
    for i,(x,z,f,w,amp,seed) in enumerate(HITS,1):
        ripple=water.createNode("ripple::2.0",f"Wave_{i}",exact_type_name=True)
        ripple.setInput(0,grid)
        k=2*math.pi/w
        ripple.setParms({"usecenter":1,"tx":x,"tz":z,"size":0.,"nripples":1,"wavelength":w,
                         "height":.045*amp,"decay":.43,"speed":math.sqrt(981*k+72*k**3)*SLOW,"seed":seed,"updatenmls":0})
        # Ripple height remains an ordinary editable parameter for node experiments.
        shifted=water.createNode("timeshift",f"Impact_clock_{i}")
        shifted.setInput(0,ripple)
        hit=f'if(ch("../ART_DIRECTION/stagger"),{f},10)'
        shifted.parm("frame").setExpression(f'max(1,$FF-{hit}+1)')
        bank=wrangle(water,f"Propagate_{i}",[previous,shifted],BANK.replace("raw*mask","raw*chf(\"gain\")*mask"))
        for name,value in (("cx",x),("cz",z),("impact",f),("lambda",w),("front",0),("gain",1.)):
            parm(bank,name,value,-5 if name in ("cx","cz") else 0,100)
        bank.parm("impact").setExpression(hit)
        bank.parm("front").setExpression('ch("../ART_DIRECTION/front")')
        bank.parm("gain").setExpression('ch("../ART_DIRECTION/amplitude")')
        bank.parm("lambda").setExpression(f'ch("../Wave_{i}/wavelength")')
        previous=bank
    normal=water.createNode("normal","Surface_normals")
    normal.setInput(0,previous)
    normal.parm("type").set(0)
    look=wrangle(water,"Reflected_sky_and_shore",[normal],WATER_LOOK)
    look.addSpareParmTuple(hou.FloatParmTemplate("eye","Camera position",3,default_value=(0.,4.5,6.2)))
    for p,axis in zip(look.parmTuple("eye"),"xyz"):
        p.setExpression(f'ch("/obj/CAM/t{axis}")')
    parm(look,"reflection",3.6)
    parm(look,"detail",0,0,1)
    look.parm("detail").setExpression('ch("../ART_DIRECTION/look_detail")')
    look.parm("reflection").setExpression('ch("../ART_DIRECTION/reflection")')
    look.setDisplayFlag(True); look.setRenderFlag(True)
    water.layoutChildren()
    material=hou.node("/shop").createNode("v_constant","Water_radiance")
    water.parm("shop_materialpath").set(material.path())
    droplets=obj.createNode("geo","DROPS",run_init_scripts=False)
    source=droplets.createNode("add","Impact_events")
    # Copy ellipsoids to a timed set of drops. Real-time vertical flight uses linear drag.
    emit=droplets.createNode("attribwrangle","Rain_and_rebound")
    emit.setInput(0,source); emit.parm("class").set(0)
    lines=[]
    for x,z,hit,w,amp,seed in HITS:
        lines.append(f'emitdrop({x},{z},chi("stagger") ? {hit} : 10,{amp},{seed},@Frame);')
    emit.parm("snippet").set(DROPS+"\n"+"\n".join(lines))
    for name in ("stagger","detail"):
        parm(emit,name,0,0,1)
    emit.parm("stagger").setExpression('ch("/obj/RAIN/ART_DIRECTION/stagger")')
    emit.parm("detail").setExpression('ch("/obj/RAIN/ART_DIRECTION/drop_detail")')
    ball=droplets.createNode("sphere","Bead")
    ball.parm("type").set("polymesh")
    copy=droplets.createNode("copytopoints","Rain_drops")
    copy.setInput(0,ball);copy.setInput(1,emit)
    copy.setDisplayFlag(True);copy.setRenderFlag(True)
    glass=hou.node("/mat").createNode("principledshader::2.0","Water_drop_IOR")
    glass.setParms({"ior":1.333,"rough":.035,"transparency":1,"basecolor_usePointColor":0,
                    "basecolorr":.99,"basecolorg":.99,"basecolorb":.99})
    droplets.parm("shop_materialpath").set(glass.path())
    key=obj.createNode("hlight","Bead_glint")
    key.parmTuple("t").set((-3,5,3))
    key.parm("light_intensity").set(5)
    droplets.layoutChildren()
    cam=obj.createNode("cam","CAM"); cam.parmTuple("t").set((0,4.5,6.2))
    cam.parm("rx").set(-math.degrees(math.atan2(4.5,6.2)))
    cam.setParms({"focal":43,"resx":768,"resy":432});cam.setDisplayFlag(False)
    out=hou.node("/out").createNode("ifd","RAIN_BEAUTY")
    out.setParms({"camera":cam.path(),"vobject":"RAIN DROPS","vm_samplesx":2,"vm_samplesy":2,
                  "vm_maxraysamples":1,"soho_foreground":1,"vm_picture":"$HIP/render/$F4.exr"})
    # Set viewport colours for live reviews; Mantra reads the identical Cd surface.
    obj.layoutChildren();hou.setFps(24)
    hou.playbar.setFrameRange(1,90);hou.playbar.setPlaybackRange(1,90);hou.setFrame(38)
    for node in (look,copy):
        g=node.geometry()
        if g is None or node.errors(): raise RuntimeError(f"{node.path()} {node.errors()}")
    water.setUserData("research_topic","water")
    path.parent.mkdir(parents=True,exist_ok=True)
    hou.hipFile.save(str(path))


DROPS = """
void bead(vector pos; vector sz; vector col) {
    int pt=addpoint(0,pos);
    setpointattrib(0,"scale",pt,sz,"set");
    setpointattrib(0,"Cd",pt,col,"set");
}
void emitdrop(float x,z; int hit; float amp; int seed; float frame) {
    float t=(frame-hit)/24.0;
    float tau=.055*t;
    float vt=981.0/3.3;
    float vimpact=156.0;
    if(t<0 && t>-.60) {
        float y=-vt*tau+(vimpact-vt)*(exp(-3.3*tau)-1)/3.3;
        bead(set(x,y,z),set(.056,.085,.056)*amp,set(.38,.66,.70));
    }
    if(chi("detail") && tau>=0 && tau<.042) {
        for(int i=0;i<5;i++) {
            float a=2*M_PI*(i+rand(seed+i)*.35)/5;
            float vy=fit01(rand(seed+i+5),12,19);
            float h=vy*tau-.5*981*tau*tau;
            if(h>0) bead(set(x+cos(a)*tau*6.5,h,z+sin(a)*tau*6.5),
                        set(.018,.027,.018)*amp,set(.46,.76,.83));
        }
    }
}
"""

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("hip",type=Path)
    build(cli.parse_args().hip.resolve())
