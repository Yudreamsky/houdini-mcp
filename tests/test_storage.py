import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from hlab import storage
from hlab.knowledge_index import INDEX_NAME


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.local = self.tmp / "local"
        self.bundle = self.tmp / "bundle"
        self.enterContext(patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": str(self.local)}))
        self.roots = self.enterContext(patch.object(storage, "bundled_libraries", return_value=(self.bundle,)))

    def fixture(self, folder, key, title, created=None):
        card = dict(id=key, kind="node", title=title, topics=["ripple"], summary="Ripple experiment", status="observed")
        if created:
            card["created_at"] = created
        path = folder / "records" / key / "card.json"
        storage.write(path, card)
        return path

    def test_bounds_and_empty_pages(self):
        for limit,offset in [(0,0), (21,0), (2,-1)]:
            with self.subTest(limit=limit, offset=offset), self.assertRaises(ValueError):
                storage.search(limit=limit, offset=offset)
        for limit in (1,20):
            self.assertEqual(storage.search(limit=limit, offset=99), {"total":0,"next_offset":None,"cards":[]})

    def test_bilingual_topics_query_order_and_rebuild(self):
        first = self.fixture(self.bundle, "a"*32, "波纹种子", "2021-05-01T12:00:00+00:00")
        second = self.fixture(self.bundle, "b"*32, "Ripple seed", "2022-05-01T12:00:00+00:00")
        os.utime(first, (1900000000,1900000000))
        os.utime(second, (1600000000,1600000000))
        for term in ("水","雨","water","ripple"):
            for keyword in ("seed","种子"):
                rows = storage.search(topic=term, kind="node", status="observed", query=keyword, limit=1)
                self.assertEqual((rows["total"],rows["next_offset"],rows["cards"][0]["id"]), (2,1,"b"*32))
        after = storage.search(query="种子",offset=1)
        self.assertEqual(after["cards"][0]["id"],"a"*32)
        (self.local/INDEX_NAME).unlink()
        self.assertEqual(storage.search(query="seed",offset=1),after)
        (self.local/INDEX_NAME).write_bytes(b"damaged generated cache")
        self.assertEqual(storage.search(query="seed",offset=1),after)

    def test_competing_libraries_external_changes_and_removed_local_copy(self):
        key = "a"*32
        self.fixture(self.bundle,key,"Bundled seed")
        p = self.fixture(self.local,key,"Local seed")
        self.assertEqual(storage.search(query="seed")["cards"][0]["title"],"Local seed")
        obj = json.loads(p.read_text(encoding="utf8")); obj["title"] = "New shape"
        p.write_text(json.dumps(obj), encoding="utf8")
        self.assertEqual(storage.search(query="seed")["total"],0)
        p.unlink()
        self.assertEqual(storage.search(topic=key)["cards"][0]["title"],"Bundled seed")
        self.roots.return_value = ()
        self.assertEqual(storage.search()["total"],0)

    def test_new_modified_and_equal_timestamp_legacy_cards(self):
        a = self.fixture(self.bundle,"a"*32,"a")
        b = self.fixture(self.bundle,"b"*32,"b")
        os.utime(a,(1600000000,1600000000));os.utime(b,(1600000000,1600000000))
        self.assertEqual([row["title"] for row in storage.search()["cards"]],["b","a"])
        os.utime(a,(1700000000,1700000000))
        self.assertEqual(storage.search(limit=1)["cards"][0]["title"],"a")
        self.fixture(self.bundle,"c"*32,"c")
        self.assertEqual(storage.search()["total"],3)

    def test_publishing_is_visible_across_processes(self):
        card = storage.record("node","first",["water"],"seed",{})
        self.assertIn("created_at",card)
        # Write-through must not depend on a subsequent call to search.
        with closing(sqlite3.connect(self.local/INDEX_NAME)) as db:
            self.assertEqual(db.execute("SELECT id FROM cards").fetchall(), [(card["id"],)])
        code = "from hlab.storage import record; record('node','child',['ripple'],'子进程',{})"
        subprocess.run([sys.executable,"-c",code],cwd=Path(storage.__file__).resolve().parents[1],check=True)
        self.assertEqual({r["title"] for r in storage.search(kind="node",topic="水")["cards"]},{"first","child"})

    def test_shipped_ripple_node_and_its_seed_experiment(self):
        self.roots.return_value = (storage.example("rain"),)
        ids = lambda rows: {r["id"] for r in rows["cards"]}
        query = storage.search(topic="雨",query="种子",limit=20)
        self.assertEqual(ids(query), ids(storage.search(topic="ripple",query="seed",limit=20)))
        self.assertIn("b6802e2bc0a54eea975fa728f2f0af03", ids(query))
        self.assertIn("a6ee37257b5e40dd827008300c57c1e6", ids(query))

    def test_parallel_writes_and_search(self):
        def write(i):
            storage.record("experiment",f"seed {i}",["rain"],"test",{})
            return storage.search(topic="水")["total"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            totals = list(pool.map(write,range(12)))
        self.assertTrue(all(1 <= n <= 12 for n in totals))
        self.assertEqual(storage.search(topic="water")["total"],12)

    def test_concurrent_readers_recover_the_same_damaged_cache(self):
        storage.record("experiment","Ripple",["rain"],"seed",{})
        (self.local/INDEX_NAME).write_bytes(b"damaged generated cache")
        ready = Barrier(4)
        def read_after_damage(_):
            ready.wait()
            return storage.search(topic="水")["total"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(read_after_damage, range(4))), [1]*4)
