"""End-to-end acceptance in a dedicated, disposable research home with a visible GUI.

Run using python -m tests.live_acceptance; the active lab must be a test fixture.
A second stdio server reconnects and restores a frozen SOP graph by persistent ID.
"""
import asyncio
import io
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from hlab.storage import home, write
from hlab.window import ensure


@asynccontextmanager
async def client():
    env = dict(os.environ,HOUDINI_RESEARCH_HOME=str(home()))
    params = StdioServerParameters(command=sys.executable,args=["-m","hlab.server"],env=env,cwd=str(Path(__file__).resolve().parents[1]))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            yield session


async def run():
    if not os.environ.get("HOUDINI_RESEARCH_HOME") or home().parent.name != ".research":
        raise RuntimeError("Use a fresh test directory under .research via HOUDINI_RESEARCH_HOME")
    if (home()/"records").exists():
        raise RuntimeError("Test directory already contains evidence; choose a fresh name")
    ensure()
    async def use(session,name,**args):
        result = await session.call_tool(name,args)
        if result.isError:
            raise AssertionError(result.content)
        images = [item for item in result.content if item.type == "image"]
        if images:
            import base64
            assert Image.open(io.BytesIO(base64.b64decode(images[0].data))).format == "PNG"
        return json.loads(result.content[0].text), len(images)

    report = {}
    async with client() as first:
        report["tools"] = [t.name for t in (await first.list_tools()).tools]
        original,_ = await use(first,"session",initialize=True)
        for pass_no in range(2):
            card,image_count = await use(first,"experiment",control="npts",samples=[32,96,192])
            assert image_count == 1
            full,_ = await use(first,"knowledge",key=card["id"])
            trials = full["details"]["samples"]
            assert [s["metrics"]["scatter_points"] for s in trials] == [32,96,192]
            assert len({s["sha256"] for s in trials})==3 and full["details"]["baseline_restored"]
            report["npts_"+str(pass_no)] = card["id"]
        seed,_ = await use(first,"experiment",control="seed",samples=[1,7,17])
        trials = (await use(first,"knowledge",key=seed["id"]))[0]["details"]["samples"]
        assert len({s["metrics"]["scatter_sha256"] for s in trials})==3
        assert {s["metrics"]["scatter_points"] for s in trials}=={original["parameters"]["npts"]}
        report["seed"] = seed["id"]
        gap,_ = await use(first,"experiment",control="second_delay",samples=[.5,.75],frame=12)
        assert gap.get("gap")
        report["gap"] = gap["gap"]
        report["node"] = (await use(first,"learn",kind="node",status="reproduced",title="Scatter 2.0 · npts",
            summary="Houdini 20.5.487，球面输入、固定种子、强制总数开启。两轮 npts=32/96/192 的实际点数分别为 32/96/192。仅限该输入。",
            topics=["scatter","fireworks","particles"],sources=[report["npts_0"],report["npts_1"]]))[0]["id"]
        report["seed_node"] = (await use(first,"learn",kind="node",status="observed",title="Scatter 2.0 · seed",
            summary="球面、固定点数 96。实测 seed=1/7/17 的点坐标序列指纹各异，点数保持 96。此条件实测一轮。",
            topics=["scatter","particles"],sources=[report["seed"]]))[0]["id"]
        comp,n = await use(first,"compare",frames=[24,36,47])
        assert n==1 and Path(comp["sheet"]).is_file()
        report["comparison"] = comp
        after,_ = await use(first,"session")
        assert after==original
        await use(first,"adjust",preset="B",changes={"second_delay":.63,"trail":.73})
        reference,_ = await use(first,"session")
        clip,n = await use(first,"motion",start=15,end=54)
        assert n==1 and clip["frames"]==40 and Path(clip["path"]).is_file()
        report["clip"] = clip
        chosen,_ = await use(first,"recipe",action="save",origin="test",title="QA · 柳枝与延迟分叉",reason="研发基线，参数由验收程序设置，尚待人工选版。")
        report["recipe"] = chosen["id"]
        await use(first,"adjust",preset="A")
    async with client() as second:
        listing,_ = await use(second,"knowledge",topic="烟花",kind="recipe")
        assert chosen["id"] in {c["id"] for c in listing["cards"]}
        restored,_ = await use(second,"recipe",action="replay",key=chosen["id"])
        assert restored["verified"] and restored["state"]["metrics"]==reference["metrics"]
        assert restored["state"]["parameters"]==reference["parameters"]
        child,_ = await use(second,"adjust",changes={"second_delay":.38})
        changed = [k for k,v in reference["parameters"].items() if v!=child["parameters"][k]]
        assert changed==["second_delay"]
        card,_ = await use(second,"recipe",action="save",origin="test",key=chosen["id"],title="QA · 提前分叉",reason="仅提前二次爆")
        report["child"] = card["id"]
        assert card["parent"]==chosen["id"]
        rejected = await second.call_tool("adjust",{"changes":{"npts":100000}})
        assert rejected.isError
        assert (await use(second,"session"))[0]==child
        report["replay"] = {"verified":True,"changed":changed,"version":reference["version"],"baseline":reference["metrics"]}
        write(home()/"acceptance.json",report)
        print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__ == "__main__":
    asyncio.run(run())
