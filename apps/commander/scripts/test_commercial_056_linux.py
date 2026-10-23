"""Native Linux candidate tests. Only temporary synthetic enrollment/config/state."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'release-candidates/commercial-0.3.56-source/agent/linux.py'

class CommercialLinuxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hara-056-native-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with patch.dict(os.environ,HOME=str(self.root),XDG_CONFIG_HOME=str(self.root/'config'),XDG_DATA_HOME=str(self.root/'data')):
            spec=importlib.util.spec_from_file_location('candidate056',SOURCE)
            self.a=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.a)
        self.cfg={'HARA_COMMANDER_URL':'https://commander.invalid','HARA_DEVICE_ID':'device-a',
                  'HARA_DEVICE_TOKEN':'synthetic-token-a','HARA_DEVICE_ARCH':'test',
                  'HARA_TENANT_ID':'tenant-a','HARA_COMMANDER_APPROVAL_MODE':'ASK_EVERY_ACTION'}
        self.write_config(self.cfg)
        self.a.configure_enrollment_state(self.cfg)

    def write_config(self,cfg):
        self.a.CONFIG_FILE.parent.mkdir(parents=True,exist_ok=True)
        self.a.CONFIG_FILE.write_text(''.join(k+'='+str(v)+'\n' for k,v in cfg.items()))

    def test_context_changes_for_other_device_tenant_origin_and_credential(self):
        original=self.a._enrollment_context(self.cfg)
        for key,value in [('HARA_DEVICE_ID','device-b'),('HARA_TENANT_ID','tenant-b'),('HARA_COMMANDER_URL','https://other.invalid'),('HARA_DEVICE_TOKEN','synthetic-token-b')]:
            self.assertNotEqual(original,self.a._enrollment_context({**self.cfg,key:value}))
        self.assertEqual(original,self.a._enrollment_context({**self.cfg,'HARA_COMMANDER_URL':'https://COMMANDER.invalid:443/'}))

    def test_origin_rejects_cleartext_userinfo_paths_query_and_fragment(self):
        for value in ['http://commander.invalid','https://user:pass@commander.invalid','https://commander.invalid/path','https://commander.invalid?q=x','https://commander.invalid/#x']:
            with self.assertRaisesRegex(ValueError,'COMMANDER_ORIGIN_INVALID'):
                self.a._enrollment_context({**self.cfg,'HARA_COMMANDER_URL':value})

    def test_state_namespaces_preserve_legacy_without_importing_other_tenant(self):
        legacy=self.a.DATA_DIR/'console-events.jsonl'
        legacy.write_text('{"event":"OLD","action_summary":"synthetic-private"}\n')
        old=legacy.read_bytes()
        first=self.a.RECEIPT_DIR
        self.a.append_console_event('A_ONLY',state='PASS')
        cfg_b={**self.cfg,'HARA_DEVICE_ID':'device-b','HARA_TENANT_ID':'tenant-b'}
        self.write_config(cfg_b);self.a.configure_enrollment_state(cfg_b)
        self.assertNotEqual(first,self.a.RECEIPT_DIR)
        with self.a._ops_connect() as db:self.assertEqual(db.execute('select count(*) from activity_events').fetchone()[0],0)
        self.assertEqual(legacy.read_bytes(),old)
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.a.show_operator_history(50,legacy=True)
        self.assertIn('OLD',output.getvalue());self.assertNotIn('synthetic-private',output.getvalue())
        self.assertEqual(legacy.read_bytes(),old)

    def session(self):
        return {'schema':'hara.commander-operator-session.v1','owner_pid':os.getpid(),
                'owner_start_marker':self.a._pid_start_marker(os.getpid()),'started_at_epoch':time.time(),
                'enrollment_context':self.a._enrollment_context(self.cfg),'agent_version':self.a.AGENT_VERSION,
                'approval_mode':'ASK_EVERY_ACTION'}

    def test_old_or_foreign_session_does_not_grant_authority(self):
        session=self.session();self.a.SESSION_FILE.write_text(json.dumps(session))
        self.assertIsNotNone(self.a.read_operator_session())
        self.write_config({**self.cfg,'HARA_DEVICE_TOKEN':'synthetic-replacement'})
        self.assertIsNone(self.a.read_operator_session())
        self.write_config(self.cfg)
        del session['enrollment_context'];self.a.SESSION_FILE.write_text(json.dumps(session))
        self.assertIsNone(self.a.read_operator_session())

    def test_future_session_fails_closed(self):
        s=self.session();s['started_at_epoch']=time.time()+120
        self.a.SESSION_FILE.write_text(json.dumps(s));self.assertIsNone(self.a.read_operator_session())

    def test_foreign_call_fails_before_filesystem_action(self):
        for field,value in [('device_id','foreign-device'),('tenant_id','foreign-tenant')]:
            with self.assertRaisesRegex(ValueError,'CALL_ENROLLMENT_MISMATCH'):
                self.a.execute_tool(self.cfg,{'tool_id':'hara.files.write',field:value,'payload':{'path':str(self.root/'must-not-exist'),'content':'x'}})
            self.assertFalse((self.root/'must-not-exist').exists())

    def test_config_replacement_denies_existing_runtime(self):
        self.write_config({**self.cfg,'HARA_DEVICE_ID':'replacement'})
        with self.assertRaisesRegex(ValueError,'ENROLLMENT_CHANGED_RESTART_REQUIRED'):
            self.a.execute_tool(self.cfg,{'tool_id':'hara.health','payload':{}})

    def test_receipts_cannot_be_read_with_foreign_enrollment(self):
        call={'request_id':'synthetic','tool_id':'hara.ping','payload':{}}
        receipt=self.a.write_receipt(self.cfg,call,'PASS',{})
        self.assertEqual(self.a.read_receipt(receipt,self.cfg)['device_id'],'device-a')
        for change in [{'HARA_DEVICE_ID':'device-b'},{'HARA_TENANT_ID':'tenant-b'},{'HARA_DEVICE_TOKEN':'other'}]:
            with self.assertRaisesRegex(ValueError,'RECEIPT_ENROLLMENT_MISMATCH'):
                self.a.read_receipt(receipt,{**self.cfg,**change})

    def test_lease_refresh_is_bounded_and_does_not_extend_local_lease(self):
        self.assertEqual(self.a._next_local_lease_refresh_delay({},1000),0)
        expires=self.a.datetime.fromtimestamp(1000+3*3600,self.a.timezone.utc).isoformat()
        self.assertEqual(self.a._next_local_lease_refresh_delay({'valid_until_utc':expires},1000),3600)

    def test_direct_access_denies_unreachable_revoked_or_wrong_device(self):
        cfg={**self.cfg,'HARA_COMMANDER_TRANSPORT_MODE':'LOCAL_TUNNEL'}
        self.write_config(cfg)
        class DB:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        lease={'transport_mode':'LOCAL_TUNNEL'}
        with patch.object(self.a,'_ops_connect',return_value=DB()),patch.object(self.a,'_active_verified_product_lease',return_value=lease):
            for response in [{},{'schema':'hara.commander-device-live-authorization.v1','ok':True,'authorized':True,'device_id':'other'},{'schema':'hara.commander-device-live-authorization.v1','ok':True,'authorized':False,'device_id':'device-a'}]:
                with patch.object(self.a,'post_json',return_value=response):
                    with self.assertRaisesRegex(ValueError,'DEVICE_REAUTH_REQUIRED'):self.a.require_local_product_authority(cfg)
            with patch.object(self.a,'post_json',side_effect=OSError('synthetic network unavailable')):
                with self.assertRaises(OSError):self.a.require_local_product_authority(cfg)
            with patch.object(self.a,'post_json',return_value={'schema':'hara.commander-device-live-authorization.v1','ok':True,'authorized':True,'device_id':'device-a'}):
                self.assertIs(self.a.require_local_product_authority(cfg),lease)

    def test_durable_console_omits_private_summary_and_keeps_request(self):
        self.a.append_console_event('TEST',{'tool_id':'hara.process.run','request_id':'synthetic-id','payload':{'command':'private-unpersisted-string'}})
        data=self.a.CONSOLE_EVENTS_FILE.read_text()
        self.assertNotIn('private-unpersisted-string',data);self.assertIn('synthetic-id',data)

    def test_legacy_sqlite_history_is_read_only_and_paginated(self):
        import sqlite3
        database=self.a.DATA_DIR/'operations.sqlite3'
        with sqlite3.connect(database) as db:
            db.execute('create table activity_events(event_id integer,at_utc text,event text,state text,tool_id text,function_id text,request_id text,error_code text,receipt_sha256 text)')
            for n in range(1,4):db.execute('insert into activity_events(event_id,event) values (?,?)',(n,'OLD_'+str(n)))
        before=database.read_bytes();output=io.StringIO()
        with contextlib.redirect_stdout(output):self.a.show_operator_history(1,3,legacy=True)
        self.assertIn('OLD_2',output.getvalue());self.assertNotIn('OLD_3',output.getvalue())
        self.assertIn('history legacy 1 2',output.getvalue());self.assertEqual(database.read_bytes(),before)

    def test_loopback_origin_is_not_a_tenant_credential(self):
        from types import SimpleNamespace
        handler=self.a._LocalPortalHandler.__new__(self.a._LocalPortalHandler)
        handler.server=SimpleNamespace(server_address=('127.0.0.1',32145),allowed_origins={'https://commander.invalid'})
        handler.headers={'Host':'127.0.0.1:32145','Origin':'https://commander.invalid'}
        self.assertFalse(handler._origin_allowed())
        handler.headers={'Host':'127.0.0.1:32145'}
        self.assertTrue(handler._origin_allowed())
        handler.headers={'Host':'dns-rebinding.invalid:32145'}
        self.assertFalse(handler._origin_allowed())

    def test_noop_mutation_retains_approval_but_reports_no_effect(self):
        call={'tool_id':'hara.files.create_directory','request_id':'no-op','payload':{'path':str(self.root),'parents':True},'_local_approval':{'state':'APPROVED','mode':'ASK_EVERY_ACTION'}}
        result=self.a.execute_tool(self.cfg,call)
        self.assertFalse(result['mutation_performed'])
        self.assertEqual(result['result']['human_approval_state'],'APPROVED')

if __name__=='__main__':unittest.main(verbosity=2)
