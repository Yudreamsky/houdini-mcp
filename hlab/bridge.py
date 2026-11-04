import time
from .storage import home, read, uid, write
from .window import active


def call(op, **args):
    return call_in(home(), op, **args)


def call_in(directory, op, **args):
    root = directory / "bridge"
    session = active(directory)
    if not session:
        raise RuntimeError("Start launch.py separately, then call session(initialize=true)")
    key = uid()
    box = root / session["id"]
    expires = time.time() + 120
    write(box / "in" / (key + ".json"), {"op": op, "args": args, "deadline": expires})
    reply = box / "out" / (key + ".json")
    while time.time() < expires:
        if reply.exists():
            result = read(reply)
            reply.unlink(missing_ok=True)
            if "error" in result:
                raise RuntimeError(result["error"])
            return result["ok"]
        if read(root / "session.json")["id"] != session["id"]:
            raise RuntimeError("Houdini session changed; inspect the active window before retrying")
        time.sleep(0.08)
    raise TimeoutError(f"{op} timed out ({key}); inspect the live state before retrying")
