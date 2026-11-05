"""Run a published WFC grammar through a fresh MCP client; no Houdini session is needed."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rules import facade_request, maze_metrics, maze_request

ROOT = Path(__file__).resolve().parents[2]


async def run(args):
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Choose a new output path: {output}")
    if args.lock_from and args.case != "facade":
        raise ValueError("--lock-from applies to the facade example")
    locked = None
    if args.lock_from:
        previous = json.loads(args.lock_from.read_text(encoding="utf-8"))
        if previous["case"] != "facade":
            raise ValueError("--lock-from must name a facade result")
        locked = previous["result"]["layout"]
    request = (maze_request(args.seed) if args.case == "maze" else
               facade_request(args.seed, locked, args.lock_columns))
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "run_mcp.py")],
                                   cwd=str(ROOT), env=dict(os.environ))
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        catalog = await client.call_tool("domain_recipe", {"name": "wfc_layout"})
        if catalog.isError:
            raise RuntimeError(catalog.content[0].text)
        response = await client.call_tool("domain_recipe", dict(action="run", domain="procedural-modeling",
                                                                name="wfc_layout", arguments=request))
        if response.isError:
            raise RuntimeError(response.content[0].text)
        result = response.structuredContent or json.loads(response.content[0].text)
    payload = dict(case=args.case, request=request, result=result,
                   solver_sha256=hashlib.sha256((ROOT / "hlab/wfc.py").read_bytes()).hexdigest())
    if args.case == "maze":
        payload["checks"] = maze_metrics(result["layout"])
        if payload["checks"]["reachable"] != 143 or payload["checks"]["interior_edges"] != 142:
            raise RuntimeError("Maze connectivity/tree check failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(dict(output=str(output), case=args.case, seed=args.seed, stats=result["stats"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("maze", "facade"))
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock-from", type=Path)
    parser.add_argument("--lock-columns", type=int, default=6)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
