"""Process watchdog contract. Short intervals here are unit tests, not native SLO evidence."""
import importlib.util
import multiprocessing
from pathlib import Path
import time
import unittest
from unittest.mock import patch,MagicMock
import urllib.error

SOURCE=Path(__file__).resolve().parents[1]/'release-candidates/commercial-0.3.56-source/agent/linux.py'


def heartbeat(config,channel):
    while True:
        channel.send({'kind':'HEARTBEAT_CONFIRMED'})
        time.sleep(.015)


def stuck(config,channel):
    channel.send({'kind':'CALL','request_id':'synthetic','call_id':'synthetic',
                  'deadline':time.monotonic()+.08})
    time.sleep(60)


def ready(config,channel):
    while True:
        channel.send({'kind':'READY'})
        time.sleep(.02)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('supervisor056',SOURCE)
        self.a=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.a)
        self.config={'HARA_COMMANDER_TRANSPORT_MODE':'OUTBOUND_RELAY'}
        self.events=[]

    def guard(self,executor=stuck,hb=heartbeat,**settings):
        guard=self.a.RelaySupervisor(self.config,executor_target=executor,
               heartbeat_target=hb,report=self.events.append,
               settings={'heartbeat_stale':.15,'worker_timeout':.10,'heartbeat_interval':.02,
                         'restart_cooldown':.01,'restart_window':2,'max_restarts':2,**settings})
        self.addCleanup(guard.close)
        return guard

    def observe(self,guard,seconds=.35):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            guard.step(authorized=True);time.sleep(.003)

    def test_pre_execution_hang_does_not_stop_confirmed_heartbeat(self):
        guard=self.guard();self.observe(guard)
        self.assertGreaterEqual(guard.heartbeat_confirmations,4)
        self.assertIn('STALLED',[e['state'] for e in self.events])
        self.assertIn('RECOVERING',[e['state'] for e in self.events])
        self.assertLessEqual(guard.restart_counts['executor'],2)

    def test_recovered_requires_new_executor_and_confirmed_platform_heartbeat(self):
        counter=multiprocessing.get_context('fork').Value('i',0)
        def once(config,channel):
            with counter.get_lock():counter.value+=1;n=counter.value
            (stuck if n==1 else ready)(config,channel)
        guard=self.guard(executor=once);self.observe(guard)
        states=[e['state'] for e in self.events]
        self.assertIn('RECOVERED',states)
        self.assertGreaterEqual(counter.value,2)
        self.assertEqual(states.count('RECOVERED'),1)

    def test_alive_pid_without_confirmation_is_not_recovered(self):
        guard=self.guard(executor=ready,hb=ready);self.observe(guard)
        self.assertEqual(guard.heartbeat_confirmations,0)
        self.assertNotIn('RECOVERED',[e['state'] for e in self.events])
        self.assertIn('STALLED',[e['state'] for e in self.events])

    def test_intentional_stop_cancels_children_and_does_not_restart(self):
        guard=self.guard();guard.step(authorized=True)
        processes=[v['process'] for v in guard.children.values()]
        for _ in range(5):guard.step(authorized=False)
        self.assertTrue(all(not p.is_alive() for p in processes))
        self.assertEqual(guard.children,{})
        self.assertEqual(sum(guard.restart_counts.values()),0)

    def test_revoked_identity_stops_both_workers(self):
        def revoke(config,channel):channel.send({'kind':'REVOKED','code':'HTTP_403'});time.sleep(60)
        guard=self.guard(hb=revoke);self.observe(guard,.08)
        self.assertTrue(guard.revoked)
        self.assertEqual(guard.children,{})

    def test_restarts_have_a_finite_circuit(self):
        guard=self.guard(max_restarts=1);self.observe(guard,.4)
        self.assertEqual(guard.restart_counts['executor'],1)
        self.assertIn('DEGRADED',[e['state'] for e in self.events])
        self.assertLess(len(self.events),15)

    def test_local_tunnel_is_not_silently_routed_through_relay(self):
        with self.assertRaisesRegex(ValueError,'RELAY_TRANSPORT_REQUIRED'):
            self.a.RelaySupervisor({'HARA_COMMANDER_TRANSPORT_MODE':'LOCAL_TUNNEL'})

    def test_deadline_uses_platform_expiry_and_never_extends_on_phase_progress(self):
        call={'tool_id':'hara.files.list','expires_at_utc':self.a.datetime.fromtimestamp(time.time()+.5,self.a.timezone.utc).isoformat()}
        deadline=self.a.relay_call_deadline(call)
        self.assertLessEqual(deadline-time.monotonic(),.51)
        self.assertGreater(deadline-time.monotonic(),.1)
        with self.assertRaisesRegex(ValueError,'CALL_DEADLINE_REQUIRED'):
            self.a.relay_call_deadline({'tool_id':'hara.files.list'})

    def test_unreaped_worker_is_fenced_before_any_replacement(self):
        guard=self.guard()
        process=MagicMock();process.is_alive.return_value=True
        channel=MagicMock()
        guard.children['executor']={'process':process,'managed':{},'channel':channel}
        with patch.object(guard,'_spawn') as spawn:
            guard._restart('executor',time.monotonic())
            spawn.assert_not_called()
        self.assertTrue(guard.children['executor']['fenced'])
        self.assertEqual(guard.restart_counts['executor'],0)
        self.assertEqual(self.events[-1]['state'],'DEGRADED')
        process.is_alive.return_value=False

    def test_phase_messages_cannot_extend_a_stuck_call(self):
        def phase_spam(config,channel):
            channel.send({'kind':'CALL','request_id':'test','call_id':'test','deadline':time.monotonic()+.04})
            while True:
                channel.send({'kind':'PHASE','request_id':'test','phase':'EXECUTING'})
                time.sleep(.003)
        guard=self.guard(executor=phase_spam);self.observe(guard,.2)
        self.assertGreaterEqual(guard.restart_counts['executor'],1)

    def test_revoked_http_identity_does_not_retry_heartbeat(self):
        for code in (401,403):
            messages=[]
            with patch.object(self.a,'_relay_progress',side_effect=lambda kind,**k:messages.append({'kind':kind,**k})), \
                 patch.object(self.a,'post_json',side_effect=urllib.error.HTTPError('https://fixture.invalid',code,'fixture',{},None)), \
                 patch.object(self.a.time,'sleep',side_effect=AssertionError('must not retry')):
                self.a._relay_heartbeat_worker({'HARA_COMMANDER_URL':'https://fixture.invalid','HARA_DEVICE_TOKEN':'synthetic','HARA_DEVICE_ID':'synthetic','HARA_DEVICE_ARCH':'test'},None)
            self.assertEqual(messages[-1]['kind'],'REVOKED')
            self.assertNotIn('HEARTBEAT_CONFIRMED',[m['kind'] for m in messages])

    def test_unconfirmed_response_is_not_a_heartbeat(self):
        messages=[]
        with patch.object(self.a,'_relay_progress',side_effect=lambda kind,**k:messages.append({'kind':kind,**k})), \
             patch.object(self.a,'post_json',return_value={'ok':True}), \
             patch.object(self.a.time,'sleep',side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                self.a._relay_heartbeat_worker({'HARA_COMMANDER_URL':'https://fixture.invalid','HARA_DEVICE_TOKEN':'synthetic','HARA_DEVICE_ID':'synthetic','HARA_DEVICE_ARCH':'test'},None)
        self.assertNotIn('HEARTBEAT_CONFIRMED',[m['kind'] for m in messages])

    def test_429_heartbeat_backoff_is_bounded(self):
        delays=[]
        def sleep(delay):
            delays.append(delay)
            if len(delays)==5:raise StopIteration
        with patch.object(self.a,'post_json',side_effect=urllib.error.HTTPError('https://fixture.invalid',429,'fixture',{},None)), \
             patch.object(self.a.time,'sleep',side_effect=sleep):
            with self.assertRaises(StopIteration):
                self.a._relay_heartbeat_worker({'HARA_COMMANDER_URL':'https://fixture.invalid','HARA_DEVICE_TOKEN':'synthetic','HARA_DEVICE_ID':'synthetic','HARA_DEVICE_ARCH':'test'},None)
        self.assertEqual(delays,[30,60,60,60,60])

    def test_completion_needs_correlated_ack(self):
        config={'HARA_COMMANDER_URL':'https://fixture.invalid','HARA_DEVICE_TOKEN':'synthetic'}
        with patch.object(self.a,'post_json',return_value={'ok':True}):
            with self.assertRaisesRegex(ValueError,'CALL_COMPLETION_NOT_ACKNOWLEDGED'):
                self.a.complete(config,{'call_id':'synthetic'},'COMPLETED',{})
        with patch.object(self.a,'post_json',return_value={'ok':True,'call_id':'synthetic','state':'COMPLETED'}):
            self.assertTrue(self.a.complete(config,{'call_id':'synthetic'},'COMPLETED',{})['ok'])

    def test_http_response_has_a_byte_limit(self):
        response=MagicMock();response.status=200
        response.__enter__.return_value=response
        response.read.return_value=b'x'*(512*1024+1)
        opener=MagicMock();opener.open.return_value=response
        with patch.object(self.a,'NO_REDIRECT_OPENER',opener):
            with self.assertRaisesRegex(ValueError,'COMMANDER_RESPONSE_TOO_LARGE'):
                self.a.post_json('https://fixture.invalid','synthetic',{})
        self.assertLessEqual(response.read.call_args.args[0],512*1024+1)

    def test_managed_pty_is_terminated_before_executor_replacement(self):
        first_pid=multiprocessing.get_context('fork').Value('i',0)
        def child(config,channel):
            channel.send({'kind':'CALL','request_id':'pty','call_id':'pty','deadline':time.monotonic()+.15})
            result=self.a.process_start('sleep 60',timeout_ms=100,max_lines=5)
            with first_pid.get_lock():
                if first_pid.value==0:first_pid.value=self.a.PROCESS_SESSIONS[result['session_id']]['pid']
            time.sleep(60)
        guard=self.guard(executor=child);self.observe(guard,.5)
        self.assertGreater(first_pid.value,1)
        raw=Path('/proc/'+str(first_pid.value)+'/stat')
        if raw.exists():
            text=raw.read_text();self.assertEqual(text[text.rfind(')')+2:].split()[0],'Z')
        self.assertGreaterEqual(guard.restart_counts['executor'],1)

    def test_executor_network_backoff_does_not_look_like_a_stall(self):
        def backoff(config,channel):
            channel.send({'kind':'READY','delay':.25})
            time.sleep(.25)
        guard=self.guard(executor=backoff,worker_timeout=.04)
        self.observe(guard,.16)
        self.assertEqual(guard.restart_counts['executor'],0)

    def test_idle_polling_keeps_the_existing_ten_second_cadence(self):
        class StopWorker(BaseException):pass
        current=[0.0];delays=[]
        def sleep(delay):
            delays.append(delay);current[0]=100.0
            if len(delays)==2:raise StopWorker
        config={'HARA_COMMANDER_URL':'https://fixture.invalid','HARA_DEVICE_TOKEN':'synthetic'}
        with patch.object(self.a,'reconcile_relay_calls'),patch.object(self.a,'refresh_product_lease'), \
             patch.object(self.a,'post_json',return_value=None),patch.object(self.a.time,'monotonic',side_effect=lambda:current[0]), \
             patch.object(self.a.time,'sleep',side_effect=sleep):
            with self.assertRaises(StopWorker):self.a._relay_executor_worker(config,None)
        self.assertEqual(delays,[self.a.CALL_POLL_HOT_SECONDS,self.a.CALL_POLL_IDLE_SECONDS])


if __name__=='__main__':unittest.main(verbosity=2)
