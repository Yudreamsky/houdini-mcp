import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hlab import sop_lab
from hlab.improvements import GapReport, report
from hlab.storage import details, record, search


class ExperimentGapTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"HOUDINI_RESEARCH_HOME": directory}))
        self.enterContext(patch("hlab.storage.bundled_libraries", return_value=()))

    def test_live_sweeps_share_a_gap_and_keep_each_experiment(self):
        # Load the real sweep entry point without starting a Houdini GUI or replacing the
        # process-wide hlab.scene module used by other tests.
        spec = importlib.util.spec_from_file_location("hlab._test_scene", Path(sop_lab.__file__).with_name("scene.py"))
        scene = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"hou": Mock()}):
            spec.loader.exec_module(scene)
        parm = Mock()
        parm.node.return_value.type.return_value.nameWithCategory.return_value = "Sop/scatter::2.0"
        metrics = {"scatter_points": 64, "output_sha256": "same"}
        baseline = {"frame": 36, "parameters": {"seed": 0}, "metrics": metrics, "node_type": "Sop/scatter::2.0"}
        def capture(frame):
            return {"frame": frame, "metrics": metrics}
        with patch.multiple(scene, state=lambda: baseline, validated=Mock(), apply=Mock(),
                            capture=capture, parameter=lambda control: parm):
            parm.eval.side_effect = [0, 1, 0, 1, 0, 1]
            first = scene.sweep("seed", [0, 1])
            second = scene.sweep("seed", [0, 1])
            self.assertEqual(first["gap"], second["gap"])
            self.assertEqual(first["capability"], "experiment.no-response:sop/scatter::2.0:seed")
            self.assertEqual(details(second["id"])["details"]["gap_capability"], first["capability"])
            self.assertEqual(search(kind="gap", status="open")["total"], 1)
            self.assertEqual(search(kind="gap_observation")["total"], 2)
            for event in (first, second):
                observation = details(event["observation"])
                self.assertEqual(observation["parent"], first["gap"])
                self.assertEqual(observation["details"]["sources"], [event["id"]])
            self.assertIn(first["id"], details(first["gap"])["details"]["sources"])
            manual = report(GapReport(action="report", capability=first["capability"], topic="fireworks",
                                      signal="unexplained_result", expected="A new shape.", observed="No response.",
                                      reproduce="Repeat the seed sweep.", sources=[second["id"]]))
            self.assertFalse(manual["created"])
            self.assertEqual(manual["gap"], first["gap"])
            retest = record("experiment", "Independent retest", ["fireworks"], "Output changed at an active frame.", {})
            resolution = record("gap", "Retest", ["fireworks"], "Retest linked.",
                                {"sources": [first["gap"], retest["id"]]}, status="resolved")
            self.assertEqual(scene.sweep("seed", [0, 1])["prior_resolution"], resolution["id"])

    def test_sop_sweep_records_only_unexpected_responses(self):
        metrics = {"points": 10, "primitives": 4}
        def worker(req, directory):
            return {"baseline": {"node_type": "Sop/ripple::2.0", "version": "test", "inputs": []},
                    "samples": [{"actual": v, "metrics": metrics, "difference_from_first": {"matched": True}}
                                for v in req["values"]]}
        args = dict(action="sweep", hip="rain", node="/obj/RAIN/Wave_1", control="seed", values=[1, 2],
                    frame=38, renderer="", topic="water", query="", offset=0, limit=8, key="")
        with patch.object(sop_lab, "worker", side_effect=worker), patch.object(sop_lab, "store_witness", return_value="w"):
            expected_stasis = sop_lab.run(**args, expect_change=False)
            self.assertNotIn("gap", expected_stasis)
            self.assertNotIn("gap_capability", details(expected_stasis["id"])["details"])
            first = sop_lab.run(**args, expect_change=True)
            second = sop_lab.run(**args, expect_change=True)
            self.assertEqual(first["capability"], "experiment.prediction-mismatch:sop/ripple::2.0:seed")
            self.assertEqual(first["gap"], second["gap"])
            self.assertNotEqual(first["observation"], second["observation"])
            self.assertEqual(details(second["observation"])["details"]["sources"], [second["id"]])
