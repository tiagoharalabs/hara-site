"""Execute the real Event V2 loop with synthetic API/transport boundaries.

The Worker SQL fences are exercised separately by durable_worker_path_r163.
This does not convert the commercial polling Agent into an Event V2 client.
"""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

APP=Path(__file__).resolve().parents[1]
def load(name,relative):
    spec=importlib.util.spec_from_file_location(name,APP/relative)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

class WakeParityTests(unittest.TestCase):
    def setUp(self):
        self.loop=load('wake_fixture_loop','experimental/event_v2_agent_loop.py')
        self.wire=load('wake_fixture_transport','experimental/event_v2_websocket.py')
        self.cfg={'HARA_COMMANDER_URL':'https://synthetic.invalid','HARA_DEVICE_TOKEN':'synthetic-only','HARA_DEVICE_ID':'SYNTHETIC-A'}
        self.posts=[];self.executed=[];self.receipts=[];self.status=[];self.closed=[];self.frames=[];self.queue=[None]
        def post(url,token,body):
            self.posts.append((url,token,body));return self.queue.pop(0) if self.queue else None
        def execute(cfg,call):
            self.executed.append(call)
            self.receipts.append({'call_id':call['call_id'],'request_id':call['request_id'],'receipt_sha256':'a'*64})
        self.agent=types.SimpleNamespace(utcnow=lambda:'2026-10-25T00:00:00Z',
            post_json=post,execute_call=execute,try_write_event_v2_status=lambda **kw:self.status.append(kw) or True)
        self.transport=types.SimpleNamespace(open_event_socket=lambda *a:object(),
            close_socket=lambda sock:self.closed.append(sock),recv_event_or_keepalive=lambda sock:self.frames.pop(0),
            parse_event_frame=self.wire.parse_event_frame,DURABLE_LIVENESS_SECONDS=21600)

    def wake(self,call_id):
        raw=json.dumps({'schema':self.wire.EVENT_SCHEMA,'type':'CALL_AVAILABLE','call_id':call_id}).encode()
        return self.wire.ServerFrame(opcode=1,payload=raw,consumed=len(raw)+2)

    def test_wake_hint_claims_durable_response_and_correlates_one_receipt(self):
        claim={'schema':'hara.commander-device-call-claim.v1','call_id':'DURABLE-A','request_id':'REQUEST-A'}
        self.frames=[self.wake('FORGED-TENANT-B'),self.wake('FORGED-TENANT-B')]
        self.queue=[None,claim,None,None]
        result=self.loop.run_connected_session(self.transport,self.agent,self.cfg,max_steps=2,monotonic=lambda:0)
        self.assertEqual(self.executed,[claim]);self.assertEqual(result['drained_calls'],1)
        self.assertEqual(self.receipts,[{'call_id':'DURABLE-A','request_id':'REQUEST-A','receipt_sha256':'a'*64}])
        self.assertTrue(all(url.endswith('/api/device/calls/next') and token=='synthetic-only' and body=={} for url,token,body in self.posts))
        self.assertEqual(len(self.closed),1);self.assertFalse(self.status[-1]['connected'])

    def test_idle_transport_frames_do_not_add_http_polling(self):
        self.frames=[None,None,None]
        self.loop.run_connected_session(self.transport,self.agent,self.cfg,max_steps=3,monotonic=lambda:0)
        self.assertEqual(len(self.posts),1,'only the startup reconciliation drain is due')
        self.assertFalse(self.executed)

    def test_upgrade_failure_does_not_silently_activate_polling_fallback(self):
        def denied(*args):raise RuntimeError('EVENT_V2_UPGRADE_REJECTED')
        self.transport.open_event_socket=denied
        with self.assertRaisesRegex(RuntimeError,'UPGRADE_REJECTED'):
            self.loop.run_connected_session(self.transport,self.agent,self.cfg,max_steps=1)
        self.assertFalse(self.posts);self.assertFalse(self.executed)

    def test_api_failure_unwinds_socket_without_repeating_effect(self):
        def revoked(*args):raise RuntimeError('DEVICE_AUTH_INVALID')
        self.agent.post_json=revoked;self.frames=[self.wake('ANY')]
        with self.assertRaisesRegex(RuntimeError,'DEVICE_AUTH_INVALID'):
            self.loop.run_connected_session(self.transport,self.agent,self.cfg,max_steps=1)
        self.assertEqual(len(self.closed),1);self.assertFalse(self.executed)
        self.assertFalse(self.status[-1]['connected'])

if __name__=='__main__':unittest.main(verbosity=2)
