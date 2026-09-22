import concurrent.futures
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from houdini_mcp_local import render_jobs as jobs
from houdini_mcp_local.io_utils import atomic_json


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hip = self.root / 'source.hip'
        self.hip.write_bytes(b'immutable test scene')
        self.library = self.root / 'asset.hda'
        self.library.write_bytes(b'asset definition')
        self.patch = patch.multiple(jobs, JOBS=self.root / 'jobs', HYTHON=Path(sys.executable))
        self.patch.start()
        self.launched = []

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def start(self, request_id=None, **kwargs):
        return jobs.start_job(str(self.hip), '/out/render', 1, 3, 320, 180, '/img/out', '/img/source', '/obj/asset', kwargs.pop('parameters', {}), self.launched.append, [str(self.library)], request_id, **kwargs)

    def terminal(self, identifier, state='cancelled', frames=(1,)):
        folder = jobs.job_dir(identifier)
        outputs = []
        for frame in frames:
            item = {'frame': frame}
            for kind in ('png', 'exr'):
                path = folder / f'frame_{frame:04}.{kind}'
                path.write_bytes((b'\x89PNG\r\n\x1a\n' if kind == 'png' else b'exr') + str(frame).encode())
                item[kind] = dict(path=str(path), bytes=path.stat().st_size, sha256=jobs.digest(path))
            outputs.append(item)
        atomic_json(folder / 'status.json', dict(state=state, completed_frames=len(outputs), total_frames=3, outputs=outputs))
        return folder

    def test_concurrent_duplicate_launches_exactly_once(self):
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda _: self.start('same-request'), range(4)))
        self.assertEqual(len({v['job_id'] for v in results}), 1)
        self.assertEqual(len(self.launched), 1)

    def test_request_conflict_is_rejected(self):
        self.start('same-request')
        with self.assertRaisesRegex(ValueError, 'different render inputs'):
            self.start('same-request', parameters={'seed': 2})

    def test_new_id_allows_intentional_render_but_capacity_is_bounded(self):
        self.start('one')
        self.start('two')
        with self.assertRaisesRegex(RuntimeError, 'Two render jobs'):
            self.start('three')

    def test_preflight_failure_creates_no_job(self):
        with self.assertRaisesRegex(ValueError, 'camera missing'):
            self.start(preflight=lambda _: dict(ready=False, errors=['camera missing']))
        self.assertFalse(self.launched)
        self.assertFalse(list(jobs.JOBS.glob('*/request.json')))

    def test_cancel_is_request_not_terminal_success(self):
        identifier = self.start()['job_id']
        self.assertEqual(jobs.cancel_job(identifier)['state'], 'cancel_requested')
        with self.assertRaisesRegex(ValueError, 'active or uncertain'):
            jobs.resume_job(identifier, self.launched.append)

    def test_resume_reuses_verified_frames_and_preserves_parent(self):
        identifier = self.start()['job_id']
        parent = self.terminal(identifier)
        original = (parent / 'status.json').read_bytes()
        result = jobs.resume_job(identifier, self.launched.append)
        self.assertNotEqual(result['job_id'], identifier)
        self.assertEqual(result['reused_frames'], [1])
        self.assertEqual(result['parent_job_id'], identifier)
        self.assertEqual((parent / 'status.json').read_bytes(), original)
        self.assertEqual(jobs.resume_job(identifier, self.launched.append)['job_id'], result['job_id'])

    def test_corruption_excludes_only_damaged_frame(self):
        identifier = self.start()['job_id']
        parent = self.terminal(identifier, 'completed', (1, 2, 3))
        (parent / 'frame_0002.png').write_bytes(b'corrupt')
        result = jobs.resume_job(identifier, self.launched.append)
        self.assertEqual(result['reused_frames'], [1, 3])

    def test_tampered_snapshot_rejects_resume(self):
        identifier = self.start()['job_id']
        parent = self.terminal(identifier)
        (parent / 'asset.hda').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'HDA snapshot fingerprint'):
            jobs.resume_job(identifier, self.launched.append)

    def test_custom_sampling_and_region_are_immutable_request_inputs(self):
        args=dict(sampling={'pixel_samples':[3,4],'min_rays':1,'max_rays':9},region=[10,20,100,120])
        identifier=self.start('custom',**args)['job_id']
        self.assertEqual(self.start('custom',**args)['job_id'],identifier)
        with self.assertRaisesRegex(ValueError,'different render inputs'):
            self.start('custom',sampling={'pixel_samples':[4,4]},region=args['region'])
        folder=self.terminal(identifier)
        request=json.loads((folder/'request.json').read_text())
        request['sampling']['pixel_samples']=[32,32]
        atomic_json(folder/'request.json',request)
        with self.assertRaisesRegex(ValueError,'Frozen request manifest changed'):
            jobs.resume_job(identifier,self.launched.append)

    def test_diagnostic_artifacts_are_required_and_recursively_copied(self):
        identifier=self.start(diagnostics={'aovs':['direct_diffuse'],'denoise':True})['job_id']
        folder=self.terminal(identifier)
        state=json.loads((folder/'status.json').read_text());item=state['outputs'][0]
        request=json.loads((folder/'request.json').read_text())
        fake={'path':str(folder/'missing.png'),'sha256':'missing'}
        item['diagnostics']={'aovs':{'direct_diffuse':{'exr':fake,'png':fake}},'denoised':{'exr':fake,'png':fake}}
        self.assertEqual(jobs.verified_outputs(folder,request,[item]),[])
        for group,stem in ((item['diagnostics']['aovs']['direct_diffuse'],'aov'),(item['diagnostics']['denoised'],'denoised')):
            for kind in ('png','exr'):
                path=folder/(stem+'.'+kind);path.write_bytes(b'test')
                group[kind]={'path':str(path),'sha256':jobs.digest(path),'bytes':4}
        self.assertEqual(len(jobs.verified_outputs(folder,request,[item])),1)
        atomic_json(folder/'status.json',state)
        child=jobs.resume_job(identifier,self.launched.append)
        self.assertEqual(child['reused_frames'],[1])
        copied=child['outputs'][0]['diagnostics']['denoised']['png']
        self.assertEqual(Path(copied['path']).parent,jobs.job_dir(child['job_id']))
        Path(item['diagnostics']['denoised']['png']['path']).write_bytes(b'bad')
        self.assertEqual(jobs.verified_outputs(folder,request,[item]),[])

    def test_changed_external_input_rejects_resume_and_duplicate(self):
        texture = self.root / 'texture.exr'
        texture.write_bytes(b'original')
        dependency = dict(path=str(texture), sha256=jobs.digest(texture))
        identifier = self.start('input', preflight=lambda _: dict(ready=True, external_dependencies=[dependency]))['job_id']
        self.terminal(identifier)
        texture.write_bytes(b'changed')
        for call in (lambda: jobs.resume_job(identifier, self.launched.append), lambda: self.start('input')):
            with self.assertRaisesRegex(ValueError, 'External dependency fingerprint'):
                call()

    def test_process_reuse_is_not_a_live_worker(self):
        with patch.object(jobs, 'process_created', return_value='new-identity'):
            self.assertFalse(jobs.alive(123, 'old-identity'))

    def test_unknown_launch_is_not_automatically_retried(self):
        def timeout(_):
            raise TimeoutError('uncertain bridge outcome')
        with patch.object(self, 'launched'):
            result = jobs.start_job(str(self.hip), '/out/render', 1, 3, 320, 180, '/img/out', '/img/source', '', {}, timeout)
        self.assertEqual(result['state'], 'launch_unknown')
        with self.assertRaisesRegex(ValueError, 'active or uncertain'):
            jobs.resume_job(result['job_id'], self.launched.append)


if __name__ == '__main__':
    unittest.main()
