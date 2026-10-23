#!/usr/bin/env python3
"""Hermetic #322 probe. Synthetic control plane; no install, pairing or network.

Exit 2 means the P0 is reproduced and beta admission remains HOLD. Intervals
are shortened for a coupling test; this does not attest the 180/300 s SLOs.
"""
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]/'release-candidates/commercial-0.3.56-source/agent/linux.py'


def worker(channel,root,inject):
    os.environ['XDG_CONFIG_HOME']=str(root/'config')
    os.environ['XDG_DATA_HOME']=str(root/'data')
    spec=importlib.util.spec_from_file_location('resilience_probe',SOURCE)
    agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
    config={'HARA_COMMANDER_URL':'https://commander.invalid',
            'HARA_DEVICE_ID':'synthetic-review-device','HARA_TENANT_ID':'synthetic-review-tenant',
            'HARA_DEVICE_TOKEN':'synthetic-not-a-credential','HARA_DEVICE_ARCH':'test',
            'HARA_COMMANDER_APPROVAL_MODE':'PERSISTENT_TRUSTED'}
    agent.load_config=lambda:dict(config)
    agent.start_local_portal_server=lambda _:None
    agent.try_write_runtime_status=lambda **_:True
    agent.local_activity_heartbeat_snapshot=lambda:{}
    agent.refresh_product_lease=lambda _:None
    agent.operator_session_active=lambda:False
    agent.HEARTBEAT_SECONDS=0.03
    agent.CALL_POLL_HOT_SECONDS=0.005
    agent.CALL_POLL_IDLE_SECONDS=0.005

    def post(url,_token,_body):
        if url.endswith('/heartbeat'):
            channel.send('HEARTBEAT_CONFIRMED_SYNTHETIC')
            return {'ok':True}
        if url.endswith('/calls/next') and inject:
            return {'call_id':'synthetic','request_id':'synthetic',
                    'tool_id':'hara.files.list','payload':{'path':str(root)}}
        return None

    def reserve(_config,_call):
        channel.send('PRE_EXECUTION_STALL_INJECTED')
        # Parent terminates only this disposable probe process.
        time.sleep(30)

    agent.post_json=post
    agent.local_budget_reserve=reserve
    agent.append_console_event=lambda event,*args,**kwargs:channel.send('EVENT_'+event)
    agent.main()


def observe(inject):
    ctx=multiprocessing.get_context('fork')
    with tempfile.TemporaryDirectory(prefix='hara-056-resilience-probe-') as temporary:
        receive,send=ctx.Pipe(duplex=False)
        process=ctx.Process(target=worker,args=(send,Path(temporary),inject))
        process.start();send.close()
        events=[]
        try:
            deadline=time.monotonic()+0.6
            while time.monotonic()<deadline and process.is_alive():
                if receive.poll(0.02): events.append(receive.recv())
        finally:
            if process.is_alive(): process.terminate()
            process.join(timeout=2)
            if process.is_alive(): process.kill();process.join(timeout=2)
            receive.close()
        return {
            'heartbeat_confirmations':events.count('HEARTBEAT_CONFIRMED_SYNTHETIC'),
            'pre_execution_stall_injected':'PRE_EXECUTION_STALL_INJECTED' in events,
            'executing_observed':'EVENT_EXECUTING' in events,
            'child_reaped':not process.is_alive(),
        }


def main():
    control=observe(False)
    fault=observe(True)
    valid=control['heartbeat_confirmations']>=3 and fault['pre_execution_stall_injected']
    independent=valid and fault['heartbeat_confirmations']>=3
    result={
        'schema':'hara.commander.closed-beta.resilience-probe.v1',
        'state':'PASS_COUPLING_PROBE_ONLY' if independent else 'HOLD_P0_322',
        'probe_valid':valid,'heartbeat_independent_of_pre_execution':independent,
        'control':control,'fault':fault,'intervals_scaled':True,
        'native_180_300_second_slos_attested':False,
        'network_used':False,'installed':False,'production_release_approved':False,
    }
    print(json.dumps(result,sort_keys=True))
    return 0 if independent else 2


if __name__=='__main__':
    raise SystemExit(main())
