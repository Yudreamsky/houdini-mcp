import tempfile
import unittest
from pathlib import Path

from hlab.mechanical_rig import Joint, run, validate


class MechanicalRigTest(unittest.TestCase):
    def test_rejects_invalid_graph_and_drive_before_houdini(self):
        base = dict(part="/obj/base", kind="fixed", pivot=(0, 0, 0))
        root = Joint(**base)
        child = dict(part="/obj/rod", parent="/obj/base", kind="slider", pivot=(0, 1, 0))
        validate([root, Joint(**child, limits=(0, 2), keys=[(1, 0), (13, 1)])])
        for joints in ([root, root], [Joint(**child), root], [Joint(**base, keys=[(1, 0)])],
                       [root, Joint(**child, limits=(0, 2), keys=[(12, 3)])],
                       [root, Joint(**child, keys=[(2, 0), (2, 1)])]):
            with self.subTest(joints=joints), self.assertRaises(ValueError):
                validate(joints)

    def test_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder)/"model.hip"
            src.write_bytes(b"original")
            j = Joint(part="/obj/base", kind="fixed", pivot=(0, 0, 0))
            with self.assertRaises(FileExistsError):
                run(str(src), [j], 1, str(src), False)
            self.assertEqual(src.read_bytes(), b"original")
