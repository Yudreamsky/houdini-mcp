import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hlab.runtime import discover
from hlab.sop_lab import compare_replay
from hlab.worker_pool import seconds


class RuntimeTests(unittest.TestCase):
    def test_visible_version_overrides_highest_installed_and_explicit_environment_wins(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, clear=True):
            directory = Path(temp)
            for version in ["20.5.487", "21.0.99", "21.0.101"]:
                binaries = directory / "Side Effects Software" / ("Houdini "+version) / "bin"
                binaries.mkdir(parents=True)
                for exe in ("houdini.exe", "hython.exe"):
                    (binaries / exe).touch()
            select = lambda *versions: discover(visible_versions=versions, program_files=directory)
            self.assertIn("20.5.487", str(select("20.5.487").hython))
            selected = select()
            self.assertIn("21.0.101", selected.warning)
            with self.assertRaisesRegex(ValueError, "Multiple managed"):
                select("20.5.487", "21.0.101")
            with self.assertRaisesRegex(FileNotFoundError, "managed GUI version"):
                select("19.0")
            os.environ["HFS"] = str(selected.gui.parent.parent)
            self.assertEqual(select("20.5.487").source, "HFS")
            os.environ["HOUDINI_EXE"] = str(directory/"Side Effects Software/Houdini 21.0.99/bin/houdini.exe")
            self.assertIn("21.0.99", str(select().hython))
            os.environ["HOUDINI_EXE"] = str(directory/"missing/houdini.exe")
            with self.assertRaises(FileNotFoundError):
                select()

    def test_matching_geometry_across_versions_is_not_reproduction(self):
        self.assertEqual(compare_replay("A","A",True,True)["reuse_status"],"reproduced")
        mismatch=compare_replay("A","B",True,True)
        self.assertFalse(mismatch["verified"])
        self.assertTrue(mismatch["geometry_match"])
        self.assertEqual(mismatch["reuse_status"], "conditions_changed")
        self.assertEqual(compare_replay("A","A",False,True)["reuse_status"], "conflict")

    def test_invalid_idle_does_not_start_a_worker(self):
        with patch.dict(os.environ,{"TEST_WORKER_IDLE":"-1"}), self.assertRaises(ValueError):
            seconds("TEST_WORKER_IDLE", 300)
