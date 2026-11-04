"""Drive two separate MCP clients through a real Ripple experiment and scene-variant replay."""
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

from hlab.storage import home,write


@asynccontextmanager
async def client():
    root=Path(__file__).resolve().parents[1]
    params=StdioServerParameters(command=sys.executable,args=[str(root/"run_mcp.py")],env=dict(os.environ))
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as c:
            await c.initialize()
            yield c


async def use(c,tool,**args):
    r=await c.call_tool(tool,args)
    if r.isError:raise RuntimeError(r.content[0].text)
    return json.loads(r.content[0].text),r


async def main():
    res={}
    async with client() as c:
        schema,_=await use(c,"node_lab",action="inspect",query="height")
        assert schema["type"]=="Sop/ripple::2.0" and len(schema["items"])==1
        res["schema"]=schema
        p=dict(action="sweep",control="height",values=[.018,.045,.09],frame=38,topic="water",renderer="/out/RAIN_BEAUTY",
               prediction="复验预期：同一输入和帧，波高增大 2.5 倍再增大 2 倍，各点位移 RMS 应同比放大。")
        trial,_=await use(c,"node_lab",**p)
        res["height"]=trial["id"]
        deltas=[s["metrics"]["rms_point_delta"] for s in trial["samples"]]
        assert abs(deltas[1]/deltas[0]-2.5)<.001 and abs(deltas[2]/deltas[1]-2)<.001
        res["rms_deltas"]=deltas
        res["wavelength"]=(await use(c,"node_lab",action="sweep",control="wavelength",values=[.34,.54,.76],topic="water"))[0]["id"]
        ev,raw=await use(c,"evidence",key=trial["id"],index=1)
        assert raw.content[1].type=="image" and ev["frame"]==38
        res["recipe"]=(await use(c,"node_lab",action="variant",node="/obj/RAIN/ART_DIRECTION",topic="water",
                witness="/obj/RAIN/Reflected_sky_and_shore",changes={"stagger":1,"front":1,"amplitude":.82,"drop_detail":1,"look_detail":1,"reflection":3.15},
                note="雨滴击水 · 错峰落点、有限波前、折射水滴"))[0]["id"]
    async with client() as c:
        replay,_=await use(c,"node_lab",action="replay",key=res["height"])
        assert replay["verified_geometry_replay"]
        res["repeat"]=replay["id"]
        independent,_=await use(c,"node_lab",action="replay",key=res["height"])
        assert independent["process"] == replay["process"] == "fresh"
        node,_=await use(c,"learn",kind="node",status="reproduced",title="Ripple 2.0 · 波高与位移",
                         summary="Houdini 20.5.487。在同一张细分平面、同一中心、波长和第38帧条件下，height 从 0.018 到 0.045 再到 0.09，点位移 RMS 分别变为 2.5 倍和 2 倍。两次重新载入同一 HIP 均复现。画面来自下游着色后的整片水面。",
                topics=["water","ripple"],sources=[independent["id"],res["repeat"]])
        res["node_card"]=node["id"]
        restored,_=await use(c,"node_lab",action="restore",key=res["recipe"])
        assert restored["verified"]
        res["restored"]=restored
        for query,required,excluded in (("水",res["node_card"],"fireworks"),("烟花",None,"water")):
            cards=(await use(c,"knowledge",topic=query,limit=20))[0]["cards"]
            assert cards and all(excluded not in row["topics"] for row in cards)
            assert required is None or any(r["id"]==required for r in cards)
        for topic,kind in (("fireworks","comparison"),("afterglow","interaction")):
            rows=(await use(c,"knowledge",topic=topic,kind=kind))[0]["cards"]
            assert rows
            if kind=="comparison":
                _,raw=await use(c,"evidence",key=rows[0]["id"],variant="B",index=1)
                assert raw.content[1].type=="image"
        shot,_=await use(c,"afterglow",action="state")
        res["smoke_controls"]=shot["live"]["controls"]
    write(home()/"shots"/"rain"/"acceptance.json",res)
    print(json.dumps(res,indent=2,ensure_ascii=True))


if __name__=="__main__":
    asyncio.run(main())
