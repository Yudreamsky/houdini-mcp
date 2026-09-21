"""Atomic JSON updates tolerate brief Windows reader/scanner sharing locks."""
import json,os,time,uuid
from pathlib import Path

def atomic_json(path,value):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value),encoding='utf-8')
    try:
        for attempt in range(20):
            try:os.replace(temp,path);return
            except PermissionError:
                if attempt==19:raise
                time.sleep(min(.02*(attempt+1),.2))
    finally:
        if temp.exists():temp.unlink()
