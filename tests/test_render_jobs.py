import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import render_jobs
from houdini_mcp_local.io_utils import atomic_json

class RenderStatusTests(unittest.TestCase):
 def test_uncertain_launch_remains_unknown_not_failed_or_complete(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(render_jobs,'JOBS',Path(tmp)):
   folder=Path(tmp)/('c'*32);folder.mkdir()
   (folder/'status.json').write_text('{"state":"queued"}')
   (folder/'launch-error.json').write_text('{"error":"bridge timeout"}')
   self.assertEqual(render_jobs.get_status('c'*32)['state'],'launch_unknown')
 def test_transient_windows_sharing_violation_is_retried(self):
  import os
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'state.json';real_replace=os.replace;calls=[]
   def replace(a,b):
    calls.append(1)
    if len(calls)<3:raise PermissionError('simulated Windows sharing lock')
    real_replace(a,b)
   with patch('houdini_mcp_local.io_utils.os.replace',side_effect=replace),patch('houdini_mcp_local.io_utils.time.sleep'):
    atomic_json(path,{'state':'running'})
   self.assertEqual(json.loads(path.read_text()),{'state':'running'})
   self.assertEqual(len(calls),3)
 def test_partial_files_and_dead_worker_are_not_completion(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(render_jobs,'JOBS',Path(tmp)),patch.object(render_jobs,'alive',return_value=False):
   folder=Path(tmp)/('a'*32);folder.mkdir()
   (folder/'status.json').write_text(json.dumps({'state':'running','completed_frames':1,'total_frames':5}))
   (folder/'process.json').write_text('{"pid":123}')
   (folder/'frame_0001.png').write_bytes(b'partial')
   self.assertEqual(render_jobs.get_status('a'*32)['state'],'interrupted')
 def test_terminal_worker_record_survives_process_exit(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(render_jobs,'JOBS',Path(tmp)),patch.object(render_jobs,'alive',return_value=False):
   folder=Path(tmp)/('b'*32);folder.mkdir()
   for state in ('completed','failed'):
    (folder/'status.json').write_text(json.dumps({'state':state,'completed_frames':1}))
    (folder/'process.json').write_text('{"pid":123}')
    self.assertEqual(render_jobs.get_status('b'*32)['state'],state)
 def test_job_id_cannot_escape_storage(self):
  for name in ('../other','x'*32,'a'*31):
   with self.assertRaises(ValueError):render_jobs.job_dir(name)

if __name__=='__main__':unittest.main()
