import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from hlab.improvements import GapReport, Proposal, propose, report
from hlab.storage import details, record, search


class ImprovementTest(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": tmp}))
        self.entry = GapReport(action="report", topic="test", capability="rig.test",
                               signal="workaround", expected="Read a socket axis", observed="Needed a separate script",
                               reproduce="Compare the two axes in the rig sample.")

    def test_concurrent_reports_share_identity_and_keep_distinct_witnesses(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(report, [self.entry]*4))
        self.assertEqual(sum(r["created"] for r in rows), 1)
        self.assertEqual(len({r["observation"] for r in rows}), 1)
        other = report(self.entry.model_copy(update={"capability":"RIG.TEST", "observed":"Second scene also needed a script"}))
        self.assertEqual(other["gap"], rows[0]["gap"])
        self.assertNotEqual(other["observation"], rows[0]["observation"])
        self.assertEqual(details(other["observation"])["parent"], other["gap"])

    def test_proposal_does_not_close_and_historical_resolution_is_returned(self):
        case = report(self.entry)
        req = Proposal(action="propose", gap=case["gap"], change="Expose both socket axes.",
                       acceptance="Report a known two-degree offset within 0.01 degrees.", sources=[case["observation"]])
        draft = propose(req)
        self.assertTrue(draft["created"])
        self.assertFalse(propose(req)["created"])
        self.assertEqual(details(case["gap"])["status"], "open")
        self.assertEqual(search(kind="improvement", topic="test")["total"], 1)
        done = record("gap", "Verified", ["test"], "Compared the two-degree fixture.",
                      {"sources":[case["gap"], case["observation"]]}, status="resolved")
        self.assertEqual(propose(req)["resolution"], done["id"])
