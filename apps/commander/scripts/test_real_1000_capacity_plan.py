#!/usr/bin/env python3
"""Meaningful offline guards for a real1k plan; no cloud or VM load."""
import importlib.util,json,copy
from pathlib import Path
p=Path(__file__).with_name("commander_real_1000_capacity_plan.py")
spec=importlib.util.spec_from_file_location("real1k_plan_test",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=0
def equal(a,b):
 global checks
 assert a==b,(a,b);checks+=1
def fails(fn,code):
 global checks
 try:fn()
 except ValueError as e:assert str(e)==code,(str(e),code)
 else:raise AssertionError("EXPECTED_"+code)
 checks+=1
host={"schema":"hara.commander-capacity-resource-snapshot.v1","role":"Nucleo","at_unix":1000,
 "memory_total_bytes":128*m.GIB,"memory_available_bytes":76*m.GIB,
 "cpu_count":16,"load_1m":2.0,"disk_available_bytes":32*m.GIB,
 "open_files_soft":1024,"open_files_hard":8192,"cgroup_v2":True,
 "cgroup_controllers":["cpu","memory","pids"]}
equal(m.host_preflight(host,now=1120)["state"],"PASS_RESOURCE_PREFLIGHT_ONLY")
for field,value,code in (
 ("memory_available_bytes",76*m.GIB-1,"CAPACITY_HOST_MEMORY"),
 ("disk_available_bytes",32*m.GIB-1,"CAPACITY_HOST_DISK"),
 ("cpu_count",8,"CAPACITY_HOST_CPU"),("load_1m",10.4,"CAPACITY_HOST_CPU"),
 ("open_files_hard",8191,"CAPACITY_HOST_FILES"),("role","Services","CAPACITY_RESOURCE_HOST"),
 ("at_unix",999.9,"CAPACITY_RESOURCE_STALE"),("at_unix",1121,"CAPACITY_RESOURCE_STALE"),
 ("at_unix",float("nan"),"CAPACITY_RESOURCE_STALE"),
 ("cgroup_v2",False,"CAPACITY_CGROUP_REQUIRED"),
 ("cgroup_controllers",["memory","pids"],"CAPACITY_CGROUP_REQUIRED")):
 sample={**host,field:value};fails(lambda:m.host_preflight(sample,now=1120),code)
guest={**host,"role":"Guest","memory_total_bytes":60*m.GIB,"memory_available_bytes":59*m.GIB,
       "cpu_count":8,"open_files_soft":8192,"disk_available_bytes":6*m.GIB,
       "nominal_vm_memory_bytes":60*m.GIB,"libvirt_nominal_memory_verified":True}
equal(m.guest_stage_preflight(guest,1000,now=1001)["new_agents"],1000)
sample={**guest,"memory_available_bytes":m.GUEST_RESERVE+500*m.RSS_MODEL_PER_AGENT}
equal(m.guest_stage_preflight(sample,1000,alive_agents=500,rss_total_bytes=20*m.GIB,
                             rss_p99_bytes=40*m.MIB,now=1001)["new_agents"],500)
fails(lambda:m.guest_stage_preflight({**sample,"memory_available_bytes":sample["memory_available_bytes"]-1},
                                    1000,alive_agents=500,now=1001),"CAPACITY_GUEST_MEMORY")
fails(lambda:m.guest_stage_preflight(guest,1000,alive_agents=1000,rss_total_bytes=52*m.GIB+1,now=1001),
      "CAPACITY_AGENT_RSS_CEILING")
fails(lambda:m.guest_stage_preflight(guest,1000,rss_p99_bytes=100*m.MIB,now=1001),"CAPACITY_GUEST_MEMORY")
for field,value,code in (
 ("memory_total_bytes",58*m.GIB,"CAPACITY_GUEST_SIZE"),
 ("open_files_soft",1024,"CAPACITY_GUEST_FILES"),("cpu_count",4,"CAPACITY_GUEST_CPU"),
 ("load_1m",5.6,"CAPACITY_GUEST_CPU"),("disk_available_bytes",6*m.GIB-1,"CAPACITY_GUEST_DISK")):
 fails(lambda:m.guest_stage_preflight({**guest,field:value},100,now=1001),code)
fails(lambda:m.guest_stage_preflight(guest,1001,now=1001),"CAPACITY_STAGE")
fails(lambda:m.guest_stage_preflight(guest,100,alive_agents=101,now=1001),"CAPACITY_ALIVE_COUNT")
fails(lambda:m.guest_stage_preflight({**guest,"nominal_vm_memory_bytes":59*m.GIB},100,now=1001),"CAPACITY_VM_NOMINAL_MEMORY_PIN")
fails(lambda:m.guest_stage_preflight({**guest,"libvirt_nominal_memory_verified":False},100,now=1001),"CAPACITY_VM_NOMINAL_MEMORY_PIN")
# /proc/MemTotal excludes a bounded amount reserved by the guest kernel.
guest_boundary={**guest,"memory_total_bytes":m.VM_BYTES-m.GUEST_KERNEL_RESERVATION_MAX}
equal(m.guest_stage_preflight(guest_boundary,100,now=1001)["state"],"PASS_RESOURCE_PREFLIGHT_ONLY")
fails(lambda:m.guest_stage_preflight({**guest_boundary,"memory_total_bytes":guest_boundary["memory_total_bytes"]-1},100,now=1001),"CAPACITY_GUEST_SIZE")
for mode in ("short","soak24"):
 b=m.budget(mode);equal(b["planned_commands"]+b["cleanup_reserved_commands"]<=b["application_http_and_d1_command_limit"],True)
 plan=m.plan(mode,"6f6e68e3-0000-0000-0000-000000000000")
 equal(plan["bulk_load_started"],False)
 equal(plan["stages"],[100,250,500,1000])
 equal(plan["real_1000_24h_passed"],False)
fails(lambda:m.plan("soak72"),"CAPACITY_MODE")
fails(lambda:m.plan("short","untrusted-or-production"),"CAPACITY_BACKEND_PIN")
b=m.Budget(10,cleanup_reserve=3);b.before_dispatch(7)
fails(lambda:b.before_dispatch(1),"CAPACITY_BUDGET_EXHAUSTED")
equal(b.used,7)
b.before_dispatch(3,cleanup=True);equal((b.used,b.cleanup_used),(10,3))
fails(lambda:b.before_dispatch(1,cleanup=True),"CAPACITY_BUDGET_EXHAUSTED")
for value in (0,-1,True,1.5):
 fails(lambda:m.Budget(10,3).before_dispatch(value),"CAPACITY_COMMAND_COUNT")
good={"backend_pin_unchanged":True,"source_pins_match":True,"actual_agents":1000,
 "actual_tenants":1000,"connected_agents":1000,"agents_with_valid_receipts":1000,
 "continuous_seconds":1200,"agent_losses":0,"tenant_or_receipt_mismatches":0,
 "duplicate_executions_or_charges":0,"unexpected_errors":0,"p95_ms":6000,
 "p99_ms":12000,"cleanup_state":"PASS","cloud_metrics_collected":True,
 "free_and_pro_quota_cases":True,"owned_mutation_replay_cases":True,"recovery_cases_pass":True}
equal(m.stage_verdict(good,"short")["state"],"PASS")
equal(m.stage_verdict(good,"soak24")["state"],"HOLD")
equal(m.stage_verdict({**good,"continuous_seconds":86400},"soak24")["state"],"PASS")
for field,value in (
 ("continuous_seconds",1199.999),("actual_agents",100),("actual_tenants",999),
 ("connected_agents",999),("agents_with_valid_receipts",999),("agent_losses",1),
 ("tenant_or_receipt_mismatches",1),("duplicate_executions_or_charges",1),
 ("unexpected_errors",1),("p95_ms",6000.001),("p99_ms",12000.001),
 ("backend_pin_unchanged",False),("source_pins_match",False),("cleanup_state","PENDING")):
 equal(m.stage_verdict({**good,field:value},"short")["state"],"HOLD")
for field in good:
 if field in ("cloud_metrics_collected","free_and_pro_quota_cases","owned_mutation_replay_cases","recovery_cases_pass"):
  equal(m.stage_verdict({**good,"continuous_seconds":86400,field:False},"soak24")["state"],"HOLD")
for duration in (float("inf"),float("nan")):
 equal(m.stage_verdict({**good,"continuous_seconds":duration},"short")["state"],"HOLD")
empty=m.stage_verdict({},"short")
equal(empty["state"],"HOLD")
equal(all(empty["checks"].values()),False)
equal(m.stage_verdict(good,"short")["seventy_two_hour_stability_certified"],False)
print(json.dumps({"state":"PASS","checks":checks,"scope":"OFFLINE_RESOURCE_BUDGET_DURATION_GUARDS",
                  "cloud_requests":0,"vm_mutations":0,"agent_processes_started":0}))
