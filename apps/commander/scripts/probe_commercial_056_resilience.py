#!/usr/bin/env python3
"""Disposable TLS control-plane fixture; real processes, SQLite, and monotonic time.

Default measures unscaled 180/300 s SLOs against the fixture, NOT a deployed
platform/VM acceptance. --smoke shortens intervals and cannot attest those SLOs.
No installation, real enrollment, Founder identity, or production endpoint.
"""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

SOURCE=Path(__file__).resolve().parents[1]/'release-candidates/commercial-0.3.56-source/agent/linux.py'
sys.path.insert(0,str(SOURCE.parent))
import linux as agent


def configure_fixture(config):
    a=agent
    root=Path(config['_fixture_root'])
    a.DATA_DIR=root/'data';a.CONFIG_FILE=root/'config/device.env'
    a.RECEIPT_DIR=a.DATA_DIR/'receipts';a.STATUS_FILE=a.DATA_DIR/'runtime-status.json'
    a.SESSION_FILE=a.DATA_DIR/'operator-session.json';a.CONSOLE_EVENTS_FILE=a.DATA_DIR/'console-events.jsonl'
    a.OPERATIONS_DB_FILE=a.DATA_DIR/'operations.sqlite3'
    a.CONFIG_FILE.parent.mkdir(parents=True,exist_ok=True)
    a.CONFIG_FILE.write_text(''.join(k+'='+str(v)+'\n' for k,v in config.items() if k.startswith('HARA_')))
    a.CONFIG_FILE.chmod(0o600)
    a.configure_enrollment_state(config)
    context=ssl.create_default_context(cafile=config['_fixture_cert'])
    a.NO_REDIRECT_OPENER=urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),a.NoRedirectHandler())
    if config['_smoke']:
        a.HEARTBEAT_SECONDS=.1;a.CALL_POLL_HOT_SECONDS=.02
        a.RELAY_CALL_LIMITS['hara.ping']=.15
    return a


def fixture_heartbeat(config,channel):
    configure_fixture(config)._relay_heartbeat_worker(config,channel)


def fixture_executor(config,channel):
    a=configure_fixture(config)
    a.refresh_product_lease=lambda _:None
    original_reserve=a.local_budget_reserve;original_execute=a.execute_tool
    if config['_case']=='sqlite':
        real_connect=sqlite3.connect
        def slow_io(*args,**kwargs):
            kwargs['timeout']=600
            return real_connect(*args,**kwargs)
        a.sqlite3.connect=slow_io
    def reserve(cfg,call):
        if config['_case']=='pre_execution' and call['request_id']=='fault':time.sleep(600)
        return original_reserve(cfg,call)
    def execute(cfg,call):
        if config['_case']=='tool' and call['request_id']=='fault':time.sleep(600)
        return original_execute(cfg,call)
    a.local_budget_reserve=reserve;a.execute_tool=execute
    a._relay_executor_worker(config,channel)


class Fixture:
    def __init__(self,root,certificate,key,case,smoke):
        self.case=case;self.started=time.monotonic();self.smoke=smoke
        self.heartbeats=[];self.events=[];self.claims={};self.completed={};self.next_call=0
        self.lock=threading.Lock();self.sqlite_lock=None
        self.outage_seconds=(.45 if smoke else 190.0) if case=='outage' else 0
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer synthetic-fixture-only':
                    self.reply(401,{'error':'DEVICE_AUTH_INVALID'});return
                size=int(self.headers.get('Content-Length','0'))
                if size>256*1024:self.reply(413,{});return
                body=json.loads(self.rfile.read(size) or b'{}')
                elapsed=time.monotonic()-fixture.started
                if self.path.endswith('/heartbeat'):
                    if elapsed<fixture.outage_seconds:self.reply(503,{'error':'FIXTURE_OFFLINE'});return
                    if body.get('device_id')!=fixture.config['HARA_DEVICE_ID']:self.reply(403,{});return
                    with fixture.lock:fixture.heartbeats.append(time.monotonic())
                    self.reply(200,{'schema':'hara.commander-device-heartbeat.v1','ok':True,
                                   'device_id':fixture.config['HARA_DEVICE_ID'],'state':'ACTIVE'});return
                if self.path.endswith('/calls/next'):
                    with fixture.lock:
                        if fixture.case=='outage' or fixture.next_call>=2:
                            call=None
                        else:
                            name='fault' if fixture.next_call==0 else 'recovered'
                            if name=='fault' and fixture.case=='sqlite':fixture.sqlite_lock.execute('BEGIN IMMEDIATE')
                            call={'schema':'hara.commander-device-call-claim.v1','call_id':name,
                                  'request_id':name,'tool_id':'hara.ping','payload':{},
                                  'expires_at_utc':(datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat()}
                            fixture.claims[name]=time.monotonic();fixture.next_call+=1
                    self.reply(200,call) if call else self.reply(204,None)
                    return
                if self.path.endswith('/calls/complete'):
                    identity=body.get('call_id')
                    with fixture.lock:
                        if identity not in fixture.claims:self.reply(409,{'error':'DEVICE_CALL_NOT_EXECUTING'});return
                        prior=fixture.completed.get(identity)
                        if prior and prior['body']!=body:self.reply(409,{'error':'IDEMPOTENCY_CONFLICT'});return
                        fixture.completed[identity]={'body':body,'at':time.monotonic()}
                    self.reply(200,{'schema':'hara.commander-device-call-result.v1','ok':True,
                                   'call_id':identity,'state':body['state']});return
                self.reply(404,{'error':'FIXTURE_ENDPOINT_UNAVAILABLE'})
            def reply(self,status,body):
                raw=json.dumps(body).encode() if body is not None else b''
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ssl.SSLEOFError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate,key)
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config={'HARA_COMMANDER_URL':'https://127.0.0.1:'+str(self.server.server_port),
                     'HARA_DEVICE_ID':'synthetic-'+case,'HARA_TENANT_ID':'synthetic-review',
                     'HARA_DEVICE_TOKEN':'synthetic-fixture-only','HARA_DEVICE_ARCH':'test',
                     'HARA_COMMANDER_APPROVAL_MODE':'PERSISTENT_TRUSTED',
                     '_fixture_root':str(root),'_fixture_cert':str(certificate),'_case':case,'_smoke':smoke}
        a=configure_fixture(self.config)
        if case=='sqlite':
            with a._ops_connect():pass
            self.sqlite_lock=sqlite3.connect(str(a.OPERATIONS_DB_FILE),check_same_thread=False)
        settings={'start_method':'spawn'}
        if smoke:settings.update(heartbeat_stale=.3,worker_timeout=.6,heartbeat_interval=.1,restart_cooldown=.01)
        self.guard=a.RelaySupervisor(self.config,heartbeat_target=fixture_heartbeat,
                 executor_target=fixture_executor,report=self.report,settings=settings)

    def report(self,event):
        self.events.append(event)
        if self.case=='sqlite' and event['state']=='RECOVERING' and self.sqlite_lock:
            self.sqlite_lock.commit()

    def result(self):
        events=[e for e in self.events if e['state']!='PHASE']
        stalled=next((e['monotonic'] for e in events if e['state']=='STALLED'),None)
        attempt=next((e['monotonic'] for e in events if e['state']=='RECOVERING'),None)
        recovered=next((e['monotonic'] for e in events if e['state']=='RECOVERED'),None)
        with self.lock:
            heartbeats=list(self.heartbeats);completed=dict(self.completed);claims=dict(self.claims)
        if self.case=='outage':
            anchor=self.started
            restored=self.started+self.outage_seconds
            confirmed=next((t for t in heartbeats if t>=restored),None)
            passed=bool(stalled and attempt and confirmed and recovered and stalled-anchor<=180 and confirmed-restored<=300)
        else:
            anchor=claims.get('fault',self.started);restored=attempt
            result=completed.get('recovered');confirmed=result['at'] if result and result['body']['state']=='COMPLETED' else None
            terminal=completed.get('fault',{}).get('body',{}).get('state')=='FAILED'
            passed=bool(terminal and stalled and attempt and recovered and confirmed and len(heartbeats)>=2 and stalled-anchor<=180 and confirmed-attempt<=300)
        return {'case':self.case,'passed':passed,'detected_seconds':None if not stalled else round(stalled-anchor,3),
                'attempt_seconds':None if not attempt else round(attempt-anchor,3),
                'functional_recovery_seconds_after_restoration':None if not confirmed or not restored else round(confirmed-restored,3),
                'heartbeat_confirmations':len(heartbeats),'restart_counts':dict(self.guard.restart_counts),
                'platform_fixture_completed_calls':{k:v['body']['state'] for k,v in completed.items()},
                'events':[{**e,'elapsed_seconds':round(e['monotonic']-self.started,3)} for e in events]}

    def close(self):
        self.guard.close()
        if self.sqlite_lock:self.sqlite_lock.close()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    fixtures=[]
    with tempfile.TemporaryDirectory(prefix='hara-056-slo-fixture-') as directory:
        root=Path(directory);certificate=root/'fixture.crt';key=root/'fixture.key'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=Commander-local-QA-only','-addext','subjectAltName=IP:127.0.0.1',
                        '-keyout',str(key),'-out',str(certificate)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        key.chmod(0o600)
        try:
            fixtures=[Fixture(root/case,certificate,key,case,args.smoke) for case in ('pre_execution','tool','sqlite','outage')]
            deadline=time.monotonic()+(12 if args.smoke else 370)
            while time.monotonic()<deadline:
                for fixture in fixtures:fixture.guard.step(authorized=True)
                if all(f.result()['passed'] for f in fixtures):break
                time.sleep(.01 if args.smoke else .1)
            results=[f.result() for f in fixtures]
            result={'schema':'hara.commander.closed-beta.resilience-probe.v2',
                    'state':'PASS_SCALED_SMOKE_ONLY' if args.smoke else 'PASS_HERMETIC_REAL_TIME_SLO_SCENARIOS',
                    'all_passed':all(r['passed'] for r in results),'intervals_scaled':args.smoke,
                    'production_default_slo_seconds':{'detect':180,'recover_after_connectivity':300},
                    'real_tls_control_plane_fixture':True,'tls_verification_disabled':False,
                    'real_process_start_method':'spawn','real_sqlite_lock_injection':True,
                    'cases':results,'native_vm_acceptance':False,'deployed_platform_acceptance':False,
                    'installed':False,'production_release_approved':False,
                    'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
            if not result['all_passed']:result['state']='HOLD_RESILIENCE_SCENARIO_FAILED'
            print(json.dumps(result,sort_keys=True),flush=True)
            return 0 if result['all_passed'] else 2
        finally:
            for fixture in fixtures:fixture.close()


if __name__=='__main__':raise SystemExit(main())
