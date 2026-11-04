"""Observe local Houdini solve/render jobs and their recorded constraint failures."""
import asyncio
import hashlib
import json
import math
import re
import statistics
from collections import deque
from pathlib import Path

from .storage import home, ident, read, uid, write


def register(manifest):
    source = Path(manifest).resolve()
    data = read(source)
    stages = data["stages"]
    if not 1 <= len(stages) <= 32:
        raise ValueError("Register 1..32 stages")
    def resolve(value):
        return str((source.parent / value).resolve())
    specs = []
    for s in stages:
        kind = s["kind"]
        if kind not in ("solve", "xpu") or int(s["count"]) < 1 or int(s.get("step", 1)) < 1:
            raise ValueError("Invalid stage type or frame range")
        if kind == "solve" and not (s.get("result") and s.get("receipt")):
            raise ValueError("Solve stages need a cache result and a terminal JSON receipt with exit_code")
        spec = dict(name=s["name"], kind=kind, first=int(s.get("first", 1)), count=int(s["count"]),
                    step=int(s.get("step", 1)), log=resolve(s["log"]))
        for key in ("receipt", "result"):
            if s.get(key):
                spec[key] = resolve(s[key])
        specs.append(spec)
    job = dict(id=uid(), title=data["title"], stages=specs)
    if data.get("events"):
        e = data["events"]
        fps = float(e["fps"])
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Event FPS must be positive")
        job["events"] = dict(path=resolve(e["path"]), fps=fps, origin=int(e["origin"]))
    write(home() / "jobs" / (job["id"] + ".json"), job)
    return job["id"]


_saved = re.compile(r"\[(\d\d):(\d\d):(\d\d)\].*?Saved Image:\s*(.+?)\s*$")
_solve = re.compile(r"^(?:F|DUST)\s+(\d+)(?:\s|$)")


def stage_status(spec):
    log = Path(spec["log"])
    first, count, step = spec["first"], spec["count"], spec["step"]
    done, last = 0, None
    saves = {}
    times = deque(maxlen=9)
    if log.is_file():
        with log.open(encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                if spec["kind"] == "solve":
                    hit = _solve.match(line)
                    if hit:
                        frame = int(hit[1])
                        if first <= frame <= first + (count-1)*step:
                            last = max(frame, last if last is not None else first)
                    continue
                hit = _saved.search(line)
                if not hit:
                    continue
                image = (log.parent / hit[4].strip('"')).resolve()
                number = re.search(r"(\d+)$",image.stem)
                if number:
                    frame = int(number[1])
                    if frame in range(first, first+count*step, step):
                        saves[frame] = (image, int(hit[1])*3600+int(hit[2])*60+int(hit[3]))
    if spec["kind"] == "xpu":
        for frame,(file,secs) in saves.items():
            if file.is_file() and file.stat().st_size:
                times.append(secs)
                done += 1
                last = max(frame,last if last is not None else frame)
    elif last is not None:
        done = (last-first)//step+1
    rc = None
    receipt = Path(spec["receipt"]) if spec.get("receipt") else None
    if receipt and receipt.is_file():
        rc = int(read(receipt)["exit_code"])
    ready = not spec.get("result") or (Path(spec["result"]).is_file() and Path(spec["result"]).stat().st_size > 0)
    if rc == 0 and spec["kind"] == "solve" and ready:
        done, last = count, first+(count-1)*step
    if rc is not None and (rc != 0 or not ready or done != count):
        state = "failed"
    elif done == count and ready and (not receipt or rc == 0):
        state = "complete"
    else:
        state = "running" if log.exists() else "pending"
    deltas = [(b-a)%86400 for a,b in zip(times,list(times)[1:])]
    eta = round(statistics.median(deltas)*(count-done)) if len(deltas)>=2 and state=="running" else None
    return dict(name=spec["name"],state=state,frames_ready=done,total=count,last_frame=last,
                stage_eta_seconds=eta,exit_code=rc)


def snapshot(job):
    stages = [stage_status(s) for s in job["stages"]]
    states = {s["state"] for s in stages}
    state = "failed" if "failed" in states else "complete" if states=={"complete"} else "pending" if states=={"pending"} else "running"
    cursor = hashlib.sha256(json.dumps(stages,sort_keys=True).encode()).hexdigest()[:16]
    return dict(job=job["id"],title=job["title"],state=state,stages=stages,cursor=cursor)


async def inspect(action, key, manifest, query, offset, limit, cursor, seconds):
    if action=="register":
        key=register(manifest)
    job=read(home()/"jobs"/(ident(key)+".json"))
    if action=="events":
        if offset<0 or not 1<=limit<=50:raise ValueError("Invalid event page")
        e=job.get("events")
        if not e or not Path(e["path"]).is_file():raise ValueError("No recorded event file available")
        rows=[r for r in read(Path(e["path"])) if any(query.casefold() in p.casefold() for p in r["pair"])]
        return dict(job=key,total=len(rows),next_offset=offset+limit if offset+limit<len(rows) else None,
                    items=[dict(frame=r["frame"],parts=r["pair"],seconds_from_origin=round((r["frame"]-e["origin"])/e["fps"],4)) for r in rows[offset:offset+limit]])
    if action not in ("register","status","wait"):raise ValueError("Use register, status, wait, or events")
    result=await asyncio.to_thread(snapshot,job)
    if action!="wait":return result
    old=cursor or result["cursor"]
    deadline=asyncio.get_running_loop().time()+max(0,min(45,seconds))
    while result["state"] not in ("complete","failed") and result["cursor"]==old:
        remaining=deadline-asyncio.get_running_loop().time()
        if remaining<=0:break
        await asyncio.sleep(min(1.0,remaining))
        result=await asyncio.to_thread(snapshot,job)
    result["changed"]=result["cursor"]!=old
    return result
