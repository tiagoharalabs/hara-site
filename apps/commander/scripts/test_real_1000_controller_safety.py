#!/usr/bin/env python3
"""Offline/native private-fixture safety checks. No cloud/SSH/device credentials."""
from __future__ import annotations
import copy, importlib.util, json, os, signal, stat, subprocess, tempfile
import threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
vm=load("capacity_vm_test","commander_real_1000_vm_manager.py")
ctl=load("capacity_ctl_test","commander_real_1000_controller.py")
plan=load("capacity_plan_test","commander_real_1000_capacity_plan.py")
RUN="cap1k-safety-native-20261013"
UUID="c8bcefb4-3f25-41b0-a07a-58c0d7956662"

class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="hara-cap1k-native-private-")
        self.root=Path(self.tmp.name);self.root.chmod(0o700);self.children=[]
    def tearDown(self):
        for proc in self.children:
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        self.tmp.cleanup()
    def child(self,source,env=None):
        source.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        source.write_text("import time\nwhile True: time.sleep(.1)\n");source.chmod(0o600)
        p=subprocess.Popen(["/usr/bin/python3","-B",str(source)],env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);self.children.append(p)
        for _ in range(100):
            value=vm.proc_identity(p.pid)
            if value is not None and value["cmd"][:3]==[b"/usr/bin/python3",b"-B",str(source).encode()]:return p,value
            time.sleep(.01)
        self.fail("child identity timeout")
    def fake_controller(self):
        c=object.__new__(ctl.Controller);c.home=self.root;c.run_id=RUN;c.token="OWNED_FAKE_TEST_TOKEN"
        c.lock=threading.RLock();c.journal=dict(rows=[],events=[],budget_used=0,cleanup_used=0)
        c.audit={};c.budget=plan.Budget(500,100)
        c.fresh=SimpleNamespace(ISSUER="https://auth.haralabs.com.br/",
            q=lambda v:"'"+str(v).replace("'","''")+"'",
            b64url_sha256=lambda v:"OWNED_TEST_HASH")
        return c
    def manager(self,source):
        m=object.__new__(vm.Manager);m.base=self.root;m.source=source
        (self.root/"queue").mkdir(mode=0o700)
        (self.root/"results").mkdir(mode=0o700)
        m.state=dict(rows={},profile={"max_agents":2},deadline_unix=time.time()+120,
            supervisor_cgroup=Path("/proc/self/cgroup").read_text().strip())
        m.verify_sources=lambda:None
        return m
    def test_atomic_private_mode_and_replacement(self):
        path=self.root/"journal.json";vm.atomic(path,{"x":1},True);vm.atomic(path,{"x":2})
        self.assertEqual(vm.secure_read(path),{"x":2});self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
    def test_private_symlink_read_rejected(self):
        p=self.root/"x.json";vm.atomic(p,{"x":1},True);link=self.root/"link.json";link.symlink_to(p)
        with self.assertRaises(OSError):vm.secure_read(link)
    def test_private_wrong_mode_rejected(self):
        p=self.root/"x.json";vm.atomic(p,{"x":1},True);p.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,"VM_FILE_UNSAFE"):vm.secure_read(p)
    def test_pid_start_guard_preserves_live_child(self):
        source=self.root/"worker.py";p,value=self.child(source)
        bad=dict(pid=p.pid,start_ticks=value["start_ticks"]+1)
        with self.assertRaisesRegex(RuntimeError,"VM_PID_START_CHANGED"):vm.stop_exact(bad,source)
        self.assertIsNone(p.poll())
        vm.stop_exact(dict(pid=p.pid,start_ticks=value["start_ticks"]),source);p.wait(timeout=3)
    def test_pid_command_guard_preserves_other_child(self):
        source=self.root/"worker.py";p,value=self.child(source)
        with self.assertRaisesRegex(RuntimeError,"VM_PID_COMMAND_CHANGED"):
            vm.stop_exact(dict(pid=p.pid,start_ticks=value["start_ticks"]),self.root/"different.py")
        self.assertIsNone(p.poll())
    def test_pid_owner_guard(self):
        source=self.root/"worker.py";p,value=self.child(source)
        with self.assertRaisesRegex(RuntimeError,"VM_PID_OWNER_CHANGED"):
            vm.identity_matches(value,source,uid=os.getuid()+1)
        self.assertIsNone(p.poll())
    def test_partial_spawn_registration_recovered_and_stopped(self):
        source=self.root/"source/apps/commander/experimental/event_v2_agent_loop.py";m=self.manager(source)
        root=m.rowroot(0);root.mkdir(mode=0o700);env=os.environ.copy();env["XDG_CONFIG_HOME"]=str(root/"xdg-config")
        p,value=self.child(source,env);m.state["rows"]["0"]=dict(index=0,device_id="HARA-DEVICE-owned",state="REGISTERED")
        m.save()
        found=m.recover_spawn_registration()
        self.assertEqual(len(found),1);self.assertEqual(m.state["rows"]["0"]["pid"],p.pid)
        self.assertEqual(m.state["rows"]["0"]["state"],"RECOVERED_PARTIAL_SPAWN")
        self.assertEqual(m.stop_all()["remaining"],0);p.wait(timeout=3)
    def test_partial_spawn_wrong_root_is_not_killed(self):
        source=self.root/"source/apps/commander/experimental/event_v2_agent_loop.py";m=self.manager(source)
        env=os.environ.copy();env["XDG_CONFIG_HOME"]=str(self.root/"unknown-root")
        p,_=self.child(source,env);m.state["rows"]["0"]=dict(index=0,state="REGISTERED")
        with self.assertRaisesRegex(RuntimeError,"VM_PARTIAL_SPAWN_SCOPE"):m.recover_spawn_registration()
        self.assertIsNone(p.poll())
    def test_partial_spawn_wrong_cgroup_is_not_killed(self):
        source=self.root/"source/apps/commander/experimental/event_v2_agent_loop.py";m=self.manager(source)
        root=m.rowroot(0);root.mkdir(mode=0o700);env=os.environ.copy();env["XDG_CONFIG_HOME"]=str(root/"xdg-config")
        p,_=self.child(source,env);m.state["rows"]["0"]=dict(index=0,state="REGISTERED")
        m.state["supervisor_cgroup"]="0::/not-this-owned-unit"
        with self.assertRaisesRegex(RuntimeError,"VM_CHILD_CGROUP_CHANGED"):m.recover_spawn_registration()
        self.assertIsNone(p.poll())
    def test_pending_queue_credentials_scrubbed(self):
        m=self.manager(self.root/"source.py")
        vm.atomic(self.root/"queue"/("a"*32+".json"),dict(action="start",records=[{"device_token":"PRIVATE_SENTINEL"}]),True)
        m.remove_credentials()
        self.assertEqual(list((self.root/"queue").glob("*.json")),[])
        self.assertTrue(m.state["credentials_removed"])
    def test_agent_cap_fails_before_new_config(self):
        m=self.manager(self.root/"source.py")
        m.state["rows"]={"0":{"index":0},"1":{"index":1}}
        with self.assertRaisesRegex(RuntimeError,"VM_SHARD_AGENT_LIMIT"):
            m.start([dict(index=2,device_id="HARA-DEVICE-owned",device_token="a"*40)])
        self.assertFalse(m.rowroot(2).exists())
    def test_duplicate_index_never_restarts(self):
        m=self.manager(self.root/"source.py");m.state["rows"]={"0":{"index":0}}
        with self.assertRaisesRegex(RuntimeError,"VM_DUPLICATE_INDEX"):
            m.start([dict(index=0,device_id="HARA-DEVICE-owned",device_token="a"*40)])
    def test_budget_parallel_exact_reservation(self):
        c=self.fake_controller();errors=[]
        def reserve():
            try:c.before("TEST")
            except Exception as exc:errors.append(str(exc))
        threads=[threading.Thread(target=reserve) for _ in range(60)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(c.budget.used,60)
        self.assertEqual(ctl.private_read(self.root/"journal.json")["budget_used"],60)
    def test_budget_preserves_cleanup_reserve(self):
        c=self.fake_controller();c.before("TEST",amount=400)
        with self.assertRaisesRegex(ValueError,"CAPACITY_BUDGET_EXHAUSTED"):c.before("TEST")
        c.before("CLEANUP",amount=100,cleanup=True)
        self.assertEqual(c.budget.used,500);self.assertEqual(c.budget.cleanup_used,100)
    def test_fixture_journal_precedes_unknown_D1_mutation(self):
        c=self.fake_controller()
        def rows(sql):
            j=ctl.private_read(self.root/"journal.json")
            self.assertEqual(len(j["rows"]),1);self.assertEqual(j["rows"][0]["state"],"PLANNED")
            return []
        c.rows=rows
        def d1(sql):
            j=ctl.private_read(self.root/"journal.json");self.assertEqual(j["rows"][0]["state"],"D1_CREATE_DISPATCH_RESERVED")
            self.assertTrue(j["rows"][0]["collision_checked"])
            raise RuntimeError("SIMULATED_D1_UNKNOWN")
        c.d1=d1
        with self.assertRaisesRegex(RuntimeError,"SIMULATED_D1_UNKNOWN"):c.create_one(0)
        self.assertEqual(len(c.journal["rows"]),1)
        self.assertTrue(Path(c.journal["rows"][0]["private_root"]).is_dir())
    def test_collision_never_authorizes_deletion_or_creation(self):
        c=self.fake_controller();c.rows=lambda sql:[{"tenant_id":"EXISTING"}]
        c.d1=lambda sql:self.fail("must not create on collision")
        with self.assertRaisesRegex(RuntimeError,"CAPACITY_IDENTITY_COLLISION"):c.create_one(0)
        self.assertFalse(c.journal["rows"][0]["collision_checked"])
        c.audit={};c.emit=lambda:None;c.save=lambda:None
        c.cleanup()
        self.assertEqual(c.audit["cleanup_state"],"PASS")
    def test_row_updates_serialized_with_journal(self):
        c=self.fake_controller();row={"index":0};c.journal["rows"]=[row]
        def change(i):
            for n in range(10):c.update_row(row,**{"field_"+str(i):n})
        threads=[threading.Thread(target=change,args=(i,)) for i in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        got=ctl.private_read(self.root/"journal.json")["rows"][0]
        self.assertEqual(got,dict(index=0,field_0=9,field_1=9,field_2=9,field_3=9))
    def test_failed_wave_persisted_before_raise(self):
        c=self.fake_controller();c.audit={"waves":[]};captured=[]
        c.emit=lambda:captured.append(copy.deepcopy(c.audit))
        c.save=lambda:None
        class ProbeError(RuntimeError):
            def __init__(self):
                super().__init__("SIMULATED_INTERNAL_ERROR")
                self.safe_diagnostics={"http_status":500,"incident_id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        def call(*args):
            self.assertEqual(captured[0]["waves"][0]["state"],"RUNNING")
            self.assertEqual(captured[0]["waves"][0]["attempts"][0]["state"],"PENDING")
            raise ProbeError()
        c.probe=SimpleNamespace(transient_call=call,ProbeError=ProbeError)
        with self.assertRaisesRegex(RuntimeError,"CAPACITY_PROBE_ERROR_SIMULATED_INTERNAL_ERROR"):
            c.wave([dict(index=0,external_subject="own",device_id="HARA-DEVICE-own")],full=False)
        self.assertEqual(captured[-1]["waves"][0]["state"],"FAIL")
        self.assertEqual(captured[-1]["waves"][0]["attempts"][0]["http_diagnostics"]["http_status"],500)
    def test_host_memory_cpu_identity_guards(self):
        c=self.fake_controller();c.config={"vm_uuid":UUID}
        good=dict(uuid=UUID,memory_kib=60*1024*1024,current_memory_kib=60*1024*1024,vcpus=8,
            memory_available_bytes=20*1024**3,cpu_count=16,quota=400000,period=100000,at_unix=time.time())
        for changes,code in (({"uuid":"wrong"},"CAPACITY_LIBVIRT_RUNTIME_PIN"),
                             ({"current_memory_kib":1024},"CAPACITY_LIBVIRT_RUNTIME_PIN"),
                             ({"memory_available_bytes":15*1024**3},"CAPACITY_HOST_RUNTIME_MEMORY"),
                             ({"quota":400001},"CAPACITY_HOST_VM_CPU_CAP")):
            with patch.object(ctl.subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout=json.dumps(dict(good,**changes)))):
                with self.assertRaisesRegex(RuntimeError,code):c.host_runtime_pin()
        with patch.object(ctl.subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout=json.dumps(good))):
            self.assertEqual(c.host_runtime_pin()["uuid"],UUID)
    def test_source_pin_drift_rejected(self):
        c=self.fake_controller();p=self.root/"source/apps/commander/public/agent/linux.py";p.parent.mkdir(parents=True);p.write_text("original")
        c.manifest={"controller_sha256":ctl.sha(Path(ctl.__file__)),"source_sha256":{"public/agent/linux.py":ctl.sha(p)}}
        c.verify_sources();p.write_text("changed")
        with self.assertRaisesRegex(RuntimeError,"CAPACITY_FROZEN_SOURCE_DRIFT"):c.verify_sources()
    def test_current_single_VM_bulk_is_held(self):
        with self.assertRaisesRegex(RuntimeError,"CAPACITY_DISTRIBUTED_ASSIGNMENTS_REQUIRED"):
            ctl.Controller(RUN,"does-not-exist",max_agents=1000,bulk_enabled=True)
    def test_malformed_run_scope_rejected(self):
        for value in ("../outside","cap1k-short","cap1k-"+"/"*20):
            with self.assertRaisesRegex(RuntimeError,"CAPACITY_RUN_ID"):ctl.validate_run_id(value)

if __name__=="__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Safety)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps(dict(state="PASS" if result.wasSuccessful() else "FAIL",checks=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),cloud_calls=0,SSH_calls=0,
        own_native_children_guarded=True,fixtures_created_in_D1=0,agent_connections_started=0),sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
