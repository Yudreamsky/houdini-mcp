"""Time a cold/cloned library and warm knowledge queries without touching the user's cards."""
import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from hlab.server import knowledge
from hlab.knowledge_index import INDEX_NAME
from hlab.storage import record


def run(count):
    with tempfile.TemporaryDirectory(prefix="houdini-knowledge-bench-") as temp, patch.dict(
            os.environ, {"HOUDINI_RESEARCH_HOME":temp}):
        for i in range(count):
            record("experiment",f"Ripple / seed {i}",["water"],"Repeated node parameter measurement",{})
        def timed_call():
            start=time.perf_counter()
            result=knowledge(topic="雨",kind="experiment",query="种子",limit=8)
            elapsed=(time.perf_counter()-start)*1000
            assert result["total"]>=count and len(result["cards"])==8
            return elapsed
        first=timed_call()
        samples=sorted(timed_call() for _ in range(15))
        (Path(temp)/INDEX_NAME).unlink()
        cold=timed_call()
        return dict(platform=platform.system(),python=sys.version.split()[0],synthetic_cards=count,
                    first_query_after_writes_ms=round(first,1),cold_rebuild_ms=round(cold,1),warm_median_ms=round(statistics.median(samples),1),
                    warm_p95_ms=round(samples[14],1),warm_calls=len(samples))


if __name__ == "__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--cards",type=int,default=1000)
    print(json.dumps(run(ap.parse_args().cards),indent=2))
