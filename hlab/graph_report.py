"""What a graph_edit batch returns. Pure Python, so it is tested without Houdini."""
import math


def same(stored, sent):
    if isinstance(stored, (int, float)) and isinstance(sent, (int, float)):
        return math.isclose(stored, sent, rel_tol=1e-6, abs_tol=1e-9)
    return type(stored) is type(sent) and stored == sent


def notable(row, op):
    """A step worth returning: it has diagnostics, or it says something the request did not."""
    if row.get("errors") or row.get("warnings"):
        return True
    kind = row["op"]
    if kind == "create":
        return not row["init_scripts"]
    if kind == "set":
        return bool(op.get("expression")) or not same(row["value"], op["value"])
    if kind == "copy":
        return any(not same(row["values"][k], v) for k, v in (op.get("set") or {}).items())
    if kind == "flags":
        return any(op.get(flag) is not None and row[flag] != op[flag] for flag in ("display", "render"))
    return False


def summary(rows, ops, label, verbose=False):
    """Step totals per op, plus every step (verbose) or only the notable ones."""
    kinds = {}
    for row in rows:
        kinds[row["op"]] = kinds.get(row["op"], 0) + 1
    listed = list(rows) if verbose else [row for row, op in zip(rows, ops) if notable(row, op)]
    return {"label": label, "count": len(rows), "ops": kinds, "omitted": len(rows) - len(listed), "steps": listed}
