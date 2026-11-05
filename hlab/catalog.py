"""Lazy domain-tool discovery with backwards-compatible direct calls."""

import json

from jsonschema import Draft202012Validator, ValidationError
from mcp import types
from mcp.server.fastmcp import FastMCP


DOMAINS = {
    "fireworks": ("session", "adjust", "observe", "experiment", "compare", "motion"),
    "afterglow": ("afterglow",),
    "mechanics": ("mechanical_rig", "mechanism", "animation_gap"),
    "render": ("karma",),
    "procedural-modeling": ("wfc_layout",),
}
DOMAIN_OF = {name: domain for domain, names in DOMAINS.items() for name in names}


def structured(payload):
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
    )


class ResearchMCP(FastMCP):
    async def list_tools(self):
        # The tool registry stays intact. Only the default wire-level list is compacted.
        return [tool for tool in await super().list_tools() if tool.name not in DOMAIN_OF]

    async def domain_recipe(self, action, domain, name, arguments):
        tools = {tool.name: tool for tool in await super().list_tools()}
        domains = {key: [n for n in names if n in tools] for key, names in DOMAINS.items()}
        domains = {key: names for key, names in domains.items() if names}
        if action not in ("catalog", "run"):
            raise ValueError("Use catalog or run")
        if domain and domain not in domains:
            raise ValueError(f"Unknown domain: {domain}")
        if name and (name not in tools or name not in DOMAIN_OF or domain and DOMAIN_OF[name] != domain):
            raise ValueError(f"Unknown domain recipe: {name}")
        if action == "catalog" and arguments:
            raise ValueError("arguments belongs to run")
        if action == "catalog" and not (domain or name):
            return structured({"domains": domains})
        if action == "run" and not name:
            raise ValueError("Choose a recipe name from the catalog")

        if action == "catalog" and not name:
            return structured(
                {
                    "domain": domain,
                    "recipes": [{"name": n, "description": tools[n].description} for n in domains[domain]],
                }
            )
        tool = tools[name]
        if action == "catalog":
            return structured(
                {"domain": DOMAIN_OF[name], **tool.model_dump(by_alias=True, exclude_none=True)}
            )
        args = {} if arguments is None else arguments
        unknown = args.keys() - tool.inputSchema.get("properties", {}).keys()
        if unknown:
            raise ValueError(f"{name}: unknown argument(s): {', '.join(sorted(unknown))}")
        try:
            Draft202012Validator(tool.inputSchema).validate(args)
        except ValidationError as exc:
            path = ".".join(map(str, exc.absolute_path))
            raise ValueError(f"{name} {path or 'arguments'}: {exc.message}") from exc

        # Reuse the registered function and FastMCP's own return conversion; preserve images.
        result = await super().call_tool(name, args)
        if isinstance(result, types.CallToolResult):
            return result
        if isinstance(result, tuple):
            content, data = result
            return types.CallToolResult(content=content, structuredContent=data)
        if isinstance(result, dict):
            return structured(result)
        return types.CallToolResult(content=list(result))
