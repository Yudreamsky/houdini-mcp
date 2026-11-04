"""Exercise capability detection, scene-error triage and proposals using a real HIP through MCP."""
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="houdini-gap-review-") as directory:
        params = StdioServerParameters(command=sys.executable, args=[str(root / "run_mcp.py")],
                                       cwd=directory, env=dict(os.environ, HOUDINI_RESEARCH_HOME=directory))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as client:
            hello = await client.initialize()
            assert "improvement" in hello.instructions
            async def call(name, **kwargs):
                res = await client.call_tool(name, kwargs)
                if res.isError:
                    raise RuntimeError(res.content[0].text)
                return res.structuredContent or json.loads(res.content[0].text)

            args = dict(hip="sample:mechanisms/FourBar.hip",
                        joints=[dict(part="/obj/Crank", kind="fixed", pivot=[0, 0, 0])])
            ids = []
            for _ in range(2):
                res = await client.call_tool("mechanical_rig", args)
                assert res.isError
                match = re.search(r"Capability gap ([a-f0-9]{32}), observation ([a-f0-9]{32})", res.content[0].text)
                assert match, res.content[0].text
                ids.append(match.groups())
            assert ids[0] == ids[1]
            gap, observation = ids[0]
            witness = (await call("knowledge", key=observation))["details"]
            assert witness["replay"]["tool"] == "mechanical_rig"
            assert witness["replay"]["arguments"]["joints"][0]["part"] == "/obj/Crank"
            assert (await call("knowledge", kind="gap", query="rig.extend-parented-obj"))["total"] == 1

            base = "/obj/CLIMBING_STUDY/"
            invalid = await client.call_tool("mechanism", dict(hip="sample:mechanisms/Climbing-support-transfer.hip",
                spec=dict(kind="transfer", payload=base+"Cart", replace_motion=True, stages=[
                    dict(frame=1021, support=base+"New_section", payload_anchor=[0,0,0], support_anchor=[0,0,0]),
                    dict(frame=1291, support=base+"Slew_base", payload_anchor=[0,3,0], support_anchor=[.05,0,0])])))
            assert invalid.isError and "not seated" in invalid.content[0].text and "Capability gap" not in invalid.content[0].text, invalid
            assert (await call("knowledge", kind="gap", topic="mechanical-animation"))["total"] == 1

            proposal = await call("improvement", request=dict(action="propose", gap=gap, sources=[observation],
                change="Offer insertion of a neutral joint between the existing parent and the part.",
                acceptance="Reopen the sample, compare Crank world transforms on frames 1–97 at neutral, then turn the new joint and verify the joint and original parent both still drive Crank."))
            assert proposal["status"] == "proposed"
            unfinished = await client.call_tool("learn", dict(kind="gap", status="resolved", title="Verified",
                summary="Draft only", topics=["mechanical-animation"], sources=[gap, observation, proposal["id"]]))
            assert unfinished.isError and "retest" in unfinished.content[0].text
        async with stdio_client(params) as (r, w), ClientSession(r, w) as fresh:
            await fresh.initialize()
            res = await fresh.call_tool("knowledge", dict(key=proposal["id"]))
            assert not res.isError
            row = res.structuredContent or json.loads(res.content[0].text)
            assert row["parent"] == gap and observation in row["details"]["sources"]
            print("Two native failures shared one gap and witness. A 50 mm seating error stayed a scene error.")
            print("Proposal with acceptance criteria retrieved by a fresh client. Premature closure rejected.")


if __name__ == "__main__":
    asyncio.run(check())
