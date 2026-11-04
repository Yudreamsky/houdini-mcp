import math
import time
from . import bridge_queue
from .storage import home, read, uid, write
from .window import active


def call(op, **args):
    return call_in(home(), op, **args)


def operation_timeout(op, args):
    if op == "motion":
        frames = max(1, min(48, args.get("end", 12) - args.get("start", 12) + 1))
        return 15 + 30 * frames
    if op == "compare":
        return 15 + 90 * max(1, min(4, len(args.get("frames", ()))))
    if op == "sweep":
        return 15 + 30 * max(1, min(7, len(args.get("samples", ()))))
    if op == "live_study":
        plans = len(args.get("variants") or {}) if args.get("action") == "compare" else len(args.get("values") or ())
        samples = min(48, max(1, plans) * len(args.get("frames") or (None,)))
        return max(120, 15 + 30 * samples)
    if op in ("capture", "graph_capture"):
        return 30
    if op == "state" or (op == "window_hip" and not args.get("hip")):
        return 15
    return 120


def unwrap(result):
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["ok"]


def call_in(directory, op, *, expected_session=None, timeout_seconds=None, **args):
    root = directory / "bridge"
    session = active(directory)
    if not session:
        raise RuntimeError("Start launch.py separately, then call session(initialize=true)")
    if expected_session is not None and session["id"] != expected_session:
        raise RuntimeError("The selected Houdini window has changed; list windows again")
    box = root / session["id"]
    timeout = operation_timeout(op, args) if timeout_seconds is None else timeout_seconds
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    end = time.monotonic() + timeout
    request = {"op": op, "args": args, "deadline": time.time() + timeout}
    ordered = session.get("protocol", 1) >= 2
    if ordered:
        name = bridge_queue.publish(box, dict(request, protocol=2))
    else:
        name = uid() + ".json"
        write(box / "in" / name, request)
    reply = box / "out" / name
    while time.monotonic() < end:
        if reply.exists():
            result = read(reply)
            reply.unlink(missing_ok=True)
            return unwrap(result)
        if read(root / "session.json")["id"] != session["id"]:
            if ordered:
                bridge_queue.withdraw(box, name, op)
            raise RuntimeError("Houdini session changed; inspect the live state before retrying")
        time.sleep(min(.08, max(0, end - time.monotonic())))
    outcome, result = bridge_queue.withdraw(box, name, op) if ordered else ("possibly_executed", None)
    if outcome == "reply":
        return unwrap(result)
    if outcome == "not_executed":
        raise TimeoutError(f"{op} timed out before execution ({name})")
    raise TimeoutError(f"{op} timed out ({name}, {outcome}); Houdini may have executed it. Inspect the live state before retrying")
