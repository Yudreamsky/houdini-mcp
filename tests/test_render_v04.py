import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from houdini_mcp_local import render_jobs as jobs
from houdini_mcp_local.render_options import options, device_evidence, cancellation_receipt
from houdini_mcp_local.render_preview import read_preview
from houdini_mcp_local.image_inspection import inspect_pixels
from houdini_mcp_local.io_utils import atomic_json


class EvidenceTests(unittest.TestCase):
    def test_options_reject_unknown_backend_and_quality(self):
        for args in [('other', 'preview'), ('mantra', 'typo')]:
            with self.assertRaises(ValueError):
                options(*args)

    def test_device_evidence_does_not_borrow_from_another_frame(self):
        log = '>>> Render frame: 97\nDevice 0\nType : Optix\nName : GPU\nContrib : 100%\n>>> Render frame: 98\n'
        self.assertTrue(device_evidence(log, 97)['verified'])
        self.assertFalse(device_evidence(log, 98)['verified'])
        self.assertFalse(device_evidence(log, 99)['verified'])
        self.assertFalse(device_evidence(log.replace('100%', '0%'), 97)['verified'])

    def test_black_is_warning_but_nonfinite_is_invalid(self):
        black = inspect_pixels([0, 0, 0] * 2, [1, 1])
        self.assertTrue(black['finite'])
        self.assertEqual(black['warnings'], ['all_black_or_empty'])
        self.assertFalse(inspect_pixels([float('nan'), 0, 0])['finite'])
        self.assertFalse(inspect_pixels([1, 0, 0], [float('inf')])['finite'])

    def test_constant_tint_and_empty_alpha_warn(self):
        self.assertEqual(inspect_pixels([1, .1, 0] * 2, [0, 0])['warnings'], ['uniform_color', 'fully_transparent'])
        self.assertEqual(inspect_pixels([1, 0, 0, 0, 1, 0], [1, 1])['warnings'], [])

    def test_cancel_signal_alone_cannot_mask_incomplete_render(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            atomic_json(folder / 'cancel.json', {})
            self.assertIsNone(cancellation_receipt(folder, [97, 98]))
            atomic_json(folder / 'renderer-stop.json', dict(frame=98, reason='cancel_requested'))
            atomic_json(folder / 'start_0097.json', {})
            self.assertIsNone(cancellation_receipt(folder, [97, 98]))
            atomic_json(folder / 'ready_0097.json', {})
            self.assertEqual(cancellation_receipt(folder, [97, 98])['frame'], 98)
            atomic_json(folder / 'start_0098.json', {})
            self.assertIsNone(cancellation_receipt(folder, [97, 98]))


class PreviewAndLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.multiple(jobs, JOBS=self.root / 'jobs', HYTHON=Path(sys.executable))
        self.patch.start()
        self.hip = self.root / 'source.hip'; self.hip.write_bytes(b'source')
        self.launched = []

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def start(self, **kwargs):
        return jobs.start_job(str(self.hip), '/out/rop', 1, 3, 320, 180, '/img/out', '/img/in', '', {}, self.launched.append, **kwargs)

    def preview(self, identifier, width=320, outside=False):
        folder = jobs.job_dir(identifier)
        path = (self.root if outside else folder) / 'frame_0001.png'
        # Header fixture tests the access boundary, not PNG decoding.
        raw = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + struct.pack('>II', width, 180) + bytes(9)
        path.write_bytes(raw)
        output = dict(frame=1, png=dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest()))
        atomic_json(folder / 'status.json', dict(state='completed', outputs=[output]))
        return path

    def test_renderer_and_quality_participate_in_dedup(self):
        first = self.start(request_id='r')
        for changed in ({'renderer': 'karma_xpu'}, {'quality': 'final'}):
            with self.assertRaisesRegex(ValueError, 'different render inputs'):
                self.start(request_id='r', **changed)
        second = self.start(renderer='karma_xpu')
        self.assertNotEqual(first['job_id'], second['job_id'])
        self.assertEqual(second['renderer'], 'karma_xpu')

    def test_native_preview_rejects_changed_png_and_unrecorded_frame(self):
        identifier = self.start()['job_id']; path = self.preview(identifier)
        metadata, raw = read_preview(identifier)
        self.assertEqual(metadata['frame'], 1)
        self.assertEqual(raw, path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'No recorded'):
            read_preview(identifier, 2)
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
            read_preview(identifier)

    def test_preview_rejects_path_escape_and_oversize_dimensions(self):
        identifier = self.start()['job_id']
        self.preview(identifier, outside=True)
        with self.assertRaisesRegex(ValueError, 'outside'):
            read_preview(identifier)
        self.preview(identifier, width=100000)
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            read_preview(identifier)

    def test_dead_worker_with_live_renderer_cannot_be_resumed(self):
        identifier = self.start()['job_id']; folder = jobs.job_dir(identifier)
        atomic_json(folder / 'process.json', {'pid': 100})
        atomic_json(folder / 'renderer-process.json', {'pid': 200})
        with patch.object(jobs, 'alive', side_effect=lambda pid, created=None: pid == 200):
            self.assertEqual(jobs.get_status(identifier)['state'], 'renderer_stopping')
            with self.assertRaisesRegex(ValueError, 'active or uncertain'):
                jobs.resume_job(identifier, self.launched.append)
        with patch.object(jobs, 'alive', return_value=False):
            self.assertEqual(jobs.get_status(identifier)['state'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
