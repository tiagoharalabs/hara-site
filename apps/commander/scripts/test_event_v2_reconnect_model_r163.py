"""New model-to-real-loop checks only; no hosted campaign or provider limit."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.model=load('reconnect_model_fixture',HERE/'commander_event_v2_reconnect_storm_model.py')
        self.loop=load('reconnect_loop_fixture',HERE.parent/'experimental/event_v2_agent_loop.py')
        self.transport=self.model.load_transport()

    def test_model_matches_connection_times_from_the_real_process_loop(self):
        policy=self.transport.ReconnectPolicy()
        for device in [0,7,499]:
            for handshake in [0,25]:
                with self.subTest(device=device,handshake=handshake):
                    now=[0.0];seen=[];units=iter(self.model.entropy(device,n) for n in [-1,0,1,2])
                    def session(*args,**kwargs):
                        seen.append(now[0])
                        if len(seen)==4:raise KeyboardInterrupt
                        now[0]+=handshake
                        raise RuntimeError('SYNTHETIC_REFUSAL')
                    def sleep(seconds):now[0]+=seconds
                    agent=types.SimpleNamespace(safe_error_code=lambda e:'SYNTHETIC_REFUSAL',utcnow=lambda:'fixture',
                        try_write_runtime_status=lambda **kw:True,try_write_event_v2_status=lambda **kw:True)
                    with patch.object(self.loop,'run_connected_session',side_effect=session):
                        with self.assertRaises(KeyboardInterrupt):
                            self.loop.run_forever(self.transport,agent,{},monotonic=lambda:now[0],sleep=sleep,random_unit=lambda:next(units))
                    self.assertEqual(seen,self.model.planned_attempt_times(policy,device,3,handshake))

    def test_model_reports_startup_and_cumulative_waves_with_explicit_scope(self):
        value=self.model.timeline_profile(self.transport.ReconnectPolicy(),500,3,0)
        self.assertEqual(value['attempts'],2000)
        self.assertEqual(value['hosted_gate'],'HOSTED_20K_HOLD')
        self.assertIsNone(value['active_connections_measured'])
        self.assertGreater(value['max_attempts_in_1s_bucket'],0)
        self.assertGreaterEqual(value['scheduled_connect_p99_s'],value['scheduled_connect_p95_s'])

    def test_existing_session_drop_does_not_reapply_startup_spreading(self):
        value=self.model.timeline_profile(self.transport.ReconnectPolicy(),500,3,0,session_drop=True)
        self.assertEqual(value['attempts'],1500)
        self.assertEqual(value['scenario'],'existing_session_drop')
        self.assertEqual(value['hosted_gate'],'HOSTED_20K_HOLD')

    def test_json_check_is_one_json_document_and_never_hosted_approval(self):
        p=subprocess.run([sys.executable,str(HERE/'commander_event_v2_reconnect_storm_model.py'),
            '--devices','500','--attempts','2','--json','--check'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        value=json.loads(p.stdout)
        self.assertEqual(value['schema'],'hara.commander-event-v2-reconnect-storm.v2')
        self.assertIs(value['policy']['full_jitter'],False)
        self.assertEqual(value['model_check'],'MODEL_PASS')
        self.assertEqual(value['hosted_gate'],'HOSTED_20K_HOLD')
        self.assertFalse(value['commercial_agent_event_v2_parity'])

    def test_invalid_model_sizes_fail_without_an_unbounded_simulation(self):
        for args in [['--devices','0'],['--devices','-1'],['--devices','20001'],['--attempts','0'],['--attempts','33']]:
            with self.subTest(args=args):
                p=subprocess.run([sys.executable,str(HERE/'commander_event_v2_reconnect_storm_model.py'),*args],capture_output=True,text=True)
                self.assertNotEqual(p.returncode,0)

if __name__=='__main__':unittest.main(verbosity=2)
