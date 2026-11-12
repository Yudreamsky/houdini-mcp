"""Read-only network inspection in Houdini. No MCP SDK dependencies in the host."""

from collections import deque
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import hou

from .storage import details, ident, read, record, sha, stored, write


def page_bounds(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Use a nonnegative offset and limit between 1 and 100")


def page(items, offset, limit):
    end = offset + limit
    return {
        "total": len(items),
        "next_offset": end if end < len(items) else None,
        "items": items[offset:end],
    }


def node_types(category="Sop", query="", offset=0, limit=20):
    page_bounds(offset, limit)
    categories = {name.casefold(): c for name, c in hou.nodeTypeCategories().items()}
    key = {"obj": "object", "rop": "driver"}.get(category.casefold(), category.casefold())
    if key not in categories:
        raise ValueError(
            "Choose a node category: " + ", ".join(sorted(c.name() for c in categories.values()))
        )
    cat = categories[key]
    needle = query.casefold()
    entries = [
        {
            "name": t.name(),
            "type": t.nameWithCategory(),
            "label": t.description(),
            "version": t.nameComponents()[-1],
        }
        for t in cat.nodeTypes().values()
        if needle in (t.name() + " " + t.description()).casefold()
    ]
    entries.sort(key=lambda t: t["name"])
    return {"category": cat.name(), **page(entries, offset, limit)}


def node_at(path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Use an absolute Houdini node path")
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Missing node: {path}")
    return node


def small_text(text):
    if len(text) <= 2048:
        return text
    return {"preview": text[:240], "length": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()}


def parm_value(p, keys):
    if keys:
        values = []
        for key in keys:
            value = key.asJSON()
            if "expression" in value:
                value["expression"] = small_text(value["expression"])
            values.append(value)
        if len(values) <= 16:
            return values
        encoded = json.dumps(values, sort_keys=True).encode()
        return {
            "keyframes": len(values),
            "first": values[0],
            "last": values[-1],
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    if isinstance(p.parmTemplate(), hou.StringParmTemplate):
        return small_text(p.unexpandedString())
    value = p.eval()
    if isinstance(value, hou.Geometry):
        data = value.data()
        return {"geometry_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if isinstance(value, hou.Ramp):
        return {
            "basis": [b.name() for b in value.basis()],
            "keys": list(value.keys()),
            "values": [list(v) if isinstance(v, tuple) else v for v in value.values()],
        }
    if value is None or isinstance(value, (int, bool, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    return small_text(p.rawValue())


def parameters(node):
    """Nondefault parameters. An entry always has its value; locked, disabled, animated, expression and reference
    appear only when set, so a plain entry is {"value": 3} and a page of nodes stays small."""
    values = {}
    # Disable-when conditions are not otherwise guaranteed current in hython.
    node.updateParmStates()
    for p in node.parms():
        try:
            is_ramp = isinstance(p.parmTemplate(), hou.RampParmTemplate)
            default = (
                p.isAtRampDefault()
                if is_ramp
                else p.isAtDefault(compare_temporary_defaults=False, compare_expressions=True)
            )
            if default:
                continue
            keys = p.keyframes()
            ref = p.getReferencedParm()
            entry = {"value": parm_value(p, keys)}
            if p.isLocked():
                entry["locked"] = True
            if p.isDisabled():
                entry["disabled"] = True
            if keys:
                entry["animated"] = True
            if keys and len(keys) == 1 and keys[0].isExpressionSet():
                entry["expression"] = {
                    "language": keys[0].expressionLanguage().name(),
                    "text": small_text(keys[0].expression()),
                }
            if ref is not None and ref.path() != p.path():
                entry["reference"] = node.relativePathTo(ref.node()) + "/" + ref.name()
            values[p.name()] = entry
        except hou.Error as exc:
            values[p.name()] = {"unavailable": str(exc)}
    return values


def node_row(root, node):
    inputs = []
    for con in node.inputConnections():
        src = con.inputNode()
        link = {
            "input": con.inputIndex(),
            "source": root.relativePathTo(src) if src else None,
            "output": con.outputIndex(),
        }
        indirect = con.subnetIndirectInput()
        if indirect is not None:
            link["subnet"] = root.relativePathTo(indirect.parent())
            link["subnet_input"] = indirect.number()
        inputs.append(link)
    flags = {}
    for key, method in (
        ("display", "isDisplayFlagSet"),
        ("render", "isRenderFlagSet"),
        ("bypass", "isBypassed"),
    ):
        if hasattr(node, method):
            flags[key] = getattr(node, method)()
    return {
        "path": node.path(),
        "relative": root.relativePathTo(node),
        "type": node.type().nameWithCategory(),
        "inputs": sorted(inputs, key=lambda c: c["input"]),
        "flags": flags,
        "parameters": parameters(node),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


def tree(root, depth):
    queue = deque([(root, 0)])
    while queue:
        node, level = queue.popleft()
        yield node
        if level < depth:
            queue.extend((n, level + 1) for n in sorted(node.children(), key=lambda n: n.name()))


def graph_read(path="/obj", depth=1, offset=0, limit=20, snapshot=False):
    page_bounds(offset, limit)
    if type(depth) is not int or not 0 <= depth <= 12:
        raise ValueError("Use depth between 0 and 12")
    root = node_at(path)
    descendants = tree(root, depth)
    root_row = node_row(root, next(descendants))
    visible = []
    saved = [root_row] if snapshot else None
    total = 0
    for node in descendants:
        on_page = offset <= total < offset + limit
        total += 1
        if snapshot or on_page:
            row = node_row(root, node)
            if snapshot:
                if total > 4095:
                    raise ValueError("Snapshot exceeds 4096 nodes; choose a narrower root or depth")
                saved.append(row)
            if on_page:
                visible.append(row)
    answer = {
        "path": path,
        "depth": depth,
        "root": root_row,
        "nodes": visible,
        "total": total,
        "next_offset": offset + limit if offset + limit < total else None,
    }
    if snapshot:
        card = record(
            "graph_snapshot",
            path,
            ["graph"],
            f"Captured {total+1} nodes at frame {hou.frame():g}.",
            {"path": path, "depth": depth, "frame": hou.frame(), "nodes": saved},
        )
        answer["snapshot"] = card["id"]
    return answer


def cook(node, frame=None):
    target = node_at(node)
    if frame is not None and (type(frame) not in (int, float) or not math.isfinite(frame)):
        raise ValueError("Choose a finite frame")
    at = hou.frame() if frame is None else frame
    sop = target.displayNode() if isinstance(target, hou.ObjNode) else target
    geo = None
    failure = []
    try:
        if isinstance(sop, hou.SopNode):
            geo = sop.geometryAtFrame(at)
        elif frame is not None:
            if not float(frame).is_integer():
                raise ValueError("Only SOP geometry supports fractional-frame cooks")
            target.cook(force=True, frame_range=(int(frame), int(frame)))
        else:
            target.cook(force=True)
    except hou.Error as exc:
        failure = [str(exc)]
    inspected = sop if isinstance(sop, hou.SopNode) else target
    result = {
        "path": target.path(),
        "type": target.type().nameWithCategory(),
        "frame": at,
        "geometry_node": None,
        "points": None,
        "primitives": None,
        "attributes": {},
        "bounds": None,
        "errors": list(dict.fromkeys([*target.errors(), *inspected.errors(), *failure])),
        "warnings": list(dict.fromkeys([*target.warnings(), *inspected.warnings()])),
    }
    if geo is not None:
        result.update(
            geometry_node=inspected.path(),
            points=geo.intrinsicValue("pointcount"),
            primitives=geo.intrinsicValue("primitivecount"),
        )
        if result["points"] or result["primitives"]:
            bounds = geo.boundingBox()
            result["bounds"] = {
                "space": "local",
                "min": list(bounds.minvec()),
                "max": list(bounds.maxvec()),
            }
        for kind, attrs in (
            ("point", geo.pointAttribs()),
            ("primitive", geo.primAttribs()),
            ("vertex", geo.vertexAttribs()),
            ("detail", geo.globalAttribs()),
        ):
            result["attributes"][kind] = [
                {"name": a.name(), "type": a.dataType().name(), "size": a.size(), "array": a.isArrayType()}
                for a in attrs
            ]
    return result


def load_recipe_graph(key):
    # This function runs inside a fresh hython process.
    from .scene import load_checkpoint

    row = details(key)
    info = row["details"]
    if row["kind"] != "recipe":
        raise ValueError("Choose a recipe")
    bundle = stored("bundles", ident(info["bundle"]) + ".cpio")
    if sha(bundle) != info["sha256"]:
        raise ValueError("Recipe bundle or checksum changed")
    root = load_checkpoint(bundle)
    hou.setFrame(info["state"]["frame"])
    nodes = []
    for node in tree(root, 12):
        if len(nodes) >= 4096:
            raise ValueError("Recipe exceeds 4096 nodes")
        nodes.append(node_row(root, node))
    return {"path": info["state"]["path"], "depth": 12, "nodes": nodes}


def recipe_reference(key):
    # A read-only diff must never import possibly scripted recipe assets into the user's GUI.
    with tempfile.TemporaryDirectory(prefix="houdini-graph-diff-") as tmp:
        output = Path(tmp) / "graph.json"
        exe = Path(hou.text.expandString("$HFS")) / "bin" / "hython.exe"
        subprocess.run(
            [str(exe), "-m", "hlab.graph_query", key, str(output)],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=90,
            check=True,
        )
        result = read(output)
        if "error" in result:
            raise ValueError(result["error"])
        return result


def lean(parms):
    """Entries as parameters() writes them. Snapshots saved earlier spelled out every false and empty state."""
    return {name: {k: v for k, v in entry.items() if k == "value" or (v is not False and v is not None)}
            if "value" in entry else entry for name, entry in parms.items()}


def diff(key, path=""):
    row = details(key)
    if row["kind"] == "graph_snapshot":
        reference = row["details"]
    elif row["kind"] == "recipe":
        reference = recipe_reference(key)
        path = path or getattr(hou.session, "hr_active_path", None)
    else:
        raise ValueError("Choose a graph_snapshot or a recipe")
    root = node_at(path or reference["path"])
    before = {r["relative"]: {**r, "parameters": lean(r["parameters"])} for r in reference["nodes"]}
    after = {root.relativePathTo(n): node_row(root, n) for n in tree(root, reference["depth"])}
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    changes = []
    for name in sorted(before.keys() & after.keys()):
        a, b = before[name], after[name]
        delta = {}
        for field in ("type", "inputs", "flags", "parameters"):
            if a[field] == b[field]:
                continue
            if field == "parameters":
                delta[field] = {
                    k: {"before": a[field].get(k), "after": b[field].get(k)}
                    for k in sorted(a[field].keys() | b[field].keys())
                    if a[field].get(k) != b[field].get(k)
                }
            else:
                delta[field] = {"before": a[field], "after": b[field]}
        if delta:
            changes.append({"relative": name, **delta})
    return {
        "key": key,
        "path": root.path(),
        "frame": hou.frame(),
        "depth": reference["depth"],
        "added": added[:100],
        "removed": removed[:100],
        "changed": changes[:100],
        "total_added": len(added),
        "total_removed": len(removed),
        "total_changed": len(changes),
    }


if __name__ == "__main__":
    try:
        payload = load_recipe_graph(ident(sys.argv[1]))
    except Exception as exc:
        write(Path(sys.argv[2]), {"error": str(exc)})
    else:
        write(Path(sys.argv[2]), payload)
