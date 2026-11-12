import unittest
from pathlib import Path
from unittest.mock import patch

from hlab import window


class WindowSessionTests(unittest.TestCase):
    def test_save_goes_to_the_selected_window_with_the_requested_path(self):
        live = [(Path("first"), {"id": "one"}), (Path("second"), {"id": "two"})]
        with patch.object(window, "registered", return_value=live), \
                patch("hlab.bridge.call_in", return_value={"status": "saved"}) as call:
            self.assertEqual(window.manage(Path("home"), "save", "two", "F:/scenes/tower.hip"), {"status": "saved"})
            window.manage(Path("home"), "save", "one")
            with self.assertRaisesRegex(ValueError, "not live"):
                window.manage(Path("home"), "save", "three")
        self.assertEqual([c.args for c in call.call_args_list], [(Path("second"), "window_save"), (Path("first"), "window_save")])
        self.assertEqual([c.kwargs for c in call.call_args_list],
                         [{"expected_session": "two", "hip": "F:/scenes/tower.hip"}, {"expected_session": "one", "hip": ""}])

    def test_unknown_action_names_every_action(self):
        with patch.object(window, "registered", return_value=[]), \
                self.assertRaisesRegex(ValueError, "list, state, open or save"):
            window.manage(Path("home"), "write", "one")
