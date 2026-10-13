#!/usr/bin/env python3
"""Plan/resource checks for an owned REAL 1,000-Agent DEV test; never launch load.

Reads only local source/resource metadata. No network, VM creation, credentials,
SQL, enrollment, Agent start, quota changes or product certification.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,re,resource,time
from pathlib import Path
from datetime import datetime,timezone

DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
VM_NAME="commander-capacity1000-20261013"
PHASES=(100,250,500,1000)
GIB=1024**3
MIB=1024**2
VM_BYTES=60*GIB
HOST_RESERVE=16*GIB
GUEST_RESERVE=4*GIB
GUEST_KERNEL_RESERVATION_MAX=1536*MIB
RSS_MODEL_PER_AGENT=56*MIB
MIN_SNAPSHOT_AGE_SECONDS=120
BASELINE_RAMP_RSS=4183265280
BASELINE_RAMP_AGENTS=100
CLEANUP_RESERVED_COMMANDS=1024
SOURCE_FILES=("public/agent/linux.py","experimental/event_v2_websocket.py",
              "experimental/event_v2_agent_loop.py","experimental/event_v2_customer_agent.py",
              "experimental/event_v2_telemetry.py","scripts/full_acceptance_dev_fixtures.py",
              "scripts/commander_event_v2_transient_live_probe.py",
              "scripts/commander_full_acceptance_real_dev_soak.py")

def require(ok,code):
    if not ok:raise ValueError(code)

def positive_int(value,code,minimum=1):
    require(type(value) is int and value>=minimum,code)
    return value

def budget(mode):
    require(mode in ("short","soak24"),"CAPACITY_MODE")
    # full cycle = hara.health + actual device.info + same-ID replay.
    costs={
        "fixture_identity_collision_read_and_create_d1":2*1000,
        "enrollment_http":1000,
        "initial_agent_durable_reconciliation_http":1000,
        "exact_owned_selection_d1_batches":4,
        "full_cycle_all_agents_each_ramp_stage":3*sum(PHASES),
        "twenty_minute_pilot_20_health_calls_per_minute":400,
        "final_full_cycle_1000":3*1000,
        "24h_ten_full_cycles_per_agent":30000 if mode=="soak24" else 0,
        "bounded_restart_and_same_ID_replay":204,
        "cross_tenant_and_free_grant_denial_checks":90,
        "owned_Pro_mutation_replay_CAS_cases":200,
        "version_and_quota_observation_allowance":500,
    }
    limit=60000 if mode=="soak24" else 20000
    planned=sum(costs.values())
    require(planned+CLEANUP_RESERVED_COMMANDS<=limit,"CAPACITY_API_BUDGET")
    return {"application_http_and_d1_command_limit":limit,
            "planned_commands":planned,"cleanup_reserved_commands":CLEANUP_RESERVED_COMMANDS,
            "unused_headroom_commands":limit-planned-CLEANUP_RESERVED_COMMANDS,
            "components":costs,"ws_initial_upgrade_limit":1000,
            "ws_reconnect_upgrade_limit":200,
            "excluded_from_application_counter":["RFC6455 control frames","WSS liveness/telemetry messages",
              "Worker internal RPCs","D1 statements executed inside HTTP routes","Cloudflare analytics operations"],
            "excluded_events_must_be_measured_separately":True,
            "cost_or_invoice_certified":False}

class Budget:
    """Fail closed before dispatch; keep a separate allowance for own cleanup."""
    def __init__(self,limit,cleanup_reserve=CLEANUP_RESERVED_COMMANDS):
        positive_int(limit,"CAPACITY_BUDGET_LIMIT")
        positive_int(cleanup_reserve,"CAPACITY_CLEANUP_RESERVE")
        require(limit>cleanup_reserve,"CAPACITY_CLEANUP_RESERVE")
        self.limit=limit;self.cleanup_reserve=cleanup_reserve;self.used=0;self.cleanup_used=0
    def before_dispatch(self,amount=1,*,cleanup=False):
        positive_int(amount,"CAPACITY_COMMAND_COUNT")
        ceiling=self.limit if cleanup else self.limit-self.cleanup_reserve
        require(self.used+amount<=ceiling,"CAPACITY_BUDGET_EXHAUSTED")
        if cleanup:
            require(self.cleanup_used+amount<=self.cleanup_reserve,"CAPACITY_CLEANUP_BUDGET_EXHAUSTED")
            self.cleanup_used+=amount
        self.used+=amount

def local_resources(role):
    require(role in ("Services","Nucleo","Guest"),"CAPACITY_RESOURCE_ROLE")
    mem={}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k,v,*_=line.split()
        if k in ("MemTotal:","MemAvailable:","SwapTotal:","SwapFree:"):
            mem[k.rstrip(":")]=int(v)*1024
    disk=Path("/var/lib/libvirt/images") if role=="Nucleo" else Path.home()
    fs=os.statvfs(disk)
    cg=Path("/sys/fs/cgroup/cgroup.controllers")
    return {"schema":"hara.commander-capacity-resource-snapshot.v1","role":role,
            "at_unix":time.time(),"at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "memory_total_bytes":mem["MemTotal"],"memory_available_bytes":mem["MemAvailable"],
            "swap_total_bytes":mem["SwapTotal"],"swap_free_bytes":mem["SwapFree"],
            "cpu_count":os.cpu_count(),"load_1m":os.getloadavg()[0],
            "disk_available_bytes":fs.f_bavail*fs.f_frsize,
            "open_files_soft":resource.getrlimit(resource.RLIMIT_NOFILE)[0],
            "open_files_hard":resource.getrlimit(resource.RLIMIT_NOFILE)[1],
            "cgroup_v2":cg.is_file(),"cgroup_controllers":cg.read_text().split() if cg.is_file() else []}

def check_snapshot(snapshot,role,now=None):
    now=time.time() if now is None else now
    require(snapshot.get("schema")=="hara.commander-capacity-resource-snapshot.v1","CAPACITY_RESOURCE_SCHEMA")
    require(snapshot.get("role")==role,"CAPACITY_RESOURCE_HOST")
    at=snapshot.get("at_unix")
    require(type(at) in (int,float) and math.isfinite(at) and 0<=now-at<=MIN_SNAPSHOT_AGE_SECONDS,"CAPACITY_RESOURCE_STALE")
    for key in ("memory_total_bytes","memory_available_bytes","cpu_count","disk_available_bytes","open_files_hard"):
        positive_int(snapshot.get(key),"CAPACITY_RESOURCE_"+key.upper())
    load=snapshot.get("load_1m")
    require(type(load) in (int,float) and math.isfinite(load) and load>=0,"CAPACITY_RESOURCE_LOAD")
    require(snapshot.get("cgroup_v2") is True and {"cpu","memory","pids"}<=set(snapshot.get("cgroup_controllers",[])),"CAPACITY_CGROUP_REQUIRED")

def host_preflight(snapshot,now=None):
    check_snapshot(snapshot,"Nucleo",now)
    require(snapshot["memory_available_bytes"]>=VM_BYTES+HOST_RESERVE,"CAPACITY_HOST_MEMORY")
    require(snapshot["cpu_count"]>=12 and snapshot["load_1m"]<snapshot["cpu_count"]*.65,"CAPACITY_HOST_CPU")
    require(snapshot["disk_available_bytes"]>=32*GIB,"CAPACITY_HOST_DISK")
    require(snapshot["open_files_hard"]>=8192,"CAPACITY_HOST_FILES")
    return {"state":"PASS_RESOURCE_PREFLIGHT_ONLY",
            "vm_memory_bytes":VM_BYTES,"host_memory_floor_bytes":HOST_RESERVE,
            "memory_available_after_full_vm_allocation_bytes":snapshot["memory_available_bytes"]-VM_BYTES,
            "vm_created":False,"agent_processes_launched":0}

def guest_stage_preflight(snapshot,count,*,alive_agents=0,rss_total_bytes=0,rss_p99_bytes=0,now=None):
    check_snapshot(snapshot,"Guest",now)
    require(count in PHASES,"CAPACITY_STAGE")
    require(type(alive_agents) is int and 0<=alive_agents<=count,"CAPACITY_ALIVE_COUNT")
    require(type(rss_total_bytes) is int and rss_total_bytes>=0,"CAPACITY_RSS")
    require(type(rss_p99_bytes) is int and rss_p99_bytes>=0,"CAPACITY_RSS_SAMPLE")
    per_agent=max(RSS_MODEL_PER_AGENT,math.ceil(rss_p99_bytes*1.35))
    additional=count-alive_agents
    needed=GUEST_RESERVE+additional*per_agent
    require(snapshot.get("nominal_vm_memory_bytes")==VM_BYTES and snapshot.get("libvirt_nominal_memory_verified") is True,"CAPACITY_VM_NOMINAL_MEMORY_PIN")
    require(snapshot["memory_total_bytes"]>=VM_BYTES-GUEST_KERNEL_RESERVATION_MAX,"CAPACITY_GUEST_SIZE")
    require(snapshot["memory_available_bytes"]>=needed,"CAPACITY_GUEST_MEMORY")
    require(rss_total_bytes<=52*GIB,"CAPACITY_AGENT_RSS_CEILING")
    require(snapshot["cpu_count"]>=8 and snapshot["load_1m"]<snapshot["cpu_count"]*.7,"CAPACITY_GUEST_CPU")
    require(snapshot["open_files_hard"]>=8192 and snapshot.get("open_files_soft",0)>=8192,"CAPACITY_GUEST_FILES")
    require(snapshot["disk_available_bytes"]>=6*GIB,"CAPACITY_GUEST_DISK")
    return {"state":"PASS_RESOURCE_PREFLIGHT_ONLY","stage_agents":count,"new_agents":additional,
            "projected_per_agent_rss_bytes":per_agent,"required_available_bytes":needed,
            "resource_estimate_is_not_capacity_evidence":True}

def stage_verdict(observation,mode):
    """Only actual evidence can close a gate; synthetic counts are insufficient."""
    require(mode in ("short","soak24"),"CAPACITY_MODE")
    required_seconds=1200 if mode=="short" else 86400
    checks={
        "exact_pinned_backend":observation.get("backend_pin_unchanged") is True,
        "signed_agent_sources_match":observation.get("source_pins_match") is True,
        "actual_1000_agents":observation.get("actual_agents")==1000,
        "actual_1000_independent_tenants":observation.get("actual_tenants")==1000,
        "actual_1000_live_connections":observation.get("connected_agents")==1000,
        "coverage_every_agent_receipt":observation.get("agents_with_valid_receipts")==1000,
        "duration":type(observation.get("continuous_seconds")) in (int,float) and
          math.isfinite(observation["continuous_seconds"]) and observation["continuous_seconds"]>=required_seconds,
        "no_agent_loss":observation.get("agent_losses")==0,
        "no_tenant_or_receipt_mismatch":observation.get("tenant_or_receipt_mismatches")==0,
        "no_duplicate_execution_or_charge":observation.get("duplicate_executions_or_charges")==0,
        "unexpected_errors_zero":observation.get("unexpected_errors")==0,
        "p95_SLO":type(observation.get("p95_ms")) in (int,float) and 0<=observation["p95_ms"]<=6000,
        "p99_SLO":type(observation.get("p99_ms")) in (int,float) and 0<=observation["p99_ms"]<=12000,
        "bounded_cleanup":observation.get("cleanup_state")=="PASS",
    }
    if mode=="soak24":
        checks["measured_D1_DO_Worker_resources"]=observation.get("cloud_metrics_collected") is True
        checks["both_owned_Free_and_Pro"]=observation.get("free_and_pro_quota_cases") is True
        checks["own_mutation_idempotency"]=observation.get("owned_mutation_replay_cases") is True
        checks["bounded_recovery"]=observation.get("recovery_cases_pass") is True
    return {"state":"PASS" if all(checks.values()) else "HOLD","checks":checks,
            "gate":"REAL_1000_SHORT" if mode=="short" else "REAL_1000_24H",
            "actual_human_OAuth_logins_certified":False,"all_public_transports_certified":False,
            "seventy_two_hour_stability_certified":False}

def plan(mode,backend_version=None):
    if backend_version is not None:
        require(re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",backend_version),"CAPACITY_BACKEND_PIN")
    return {"schema":"hara.commander-real-1000-plan.v1","state":"PREPARED_NOT_EXECUTED",
            "environment":"DEV","origin":DEV,"mode":mode,"expected_backend_version":backend_version,
            "physical_hosts":1,"isolated_vm":VM_NAME,"vm_memory_bytes":VM_BYTES,"vm_vcpus":8,
            "vm_disk_bytes":24*GIB,"vm_autostart":False,"stages":list(PHASES),
            "probe_concurrency":20,"fixture_enrollment_concurrency":2,
            "required_continuous_seconds":1200 if mode=="short" else 86400,
            "cgroup":{"MemoryHigh_bytes":52*GIB,"MemoryMax_bytes":56*GIB,"CPUQuota_percent":600,
              "TasksMax":8192,"LimitNOFILE":8192,"RuntimeMaxSec":7200 if mode=="short" else 25*3600,
              "Restart":"no","KillMode":"mixed"},
            "resource_checks":{"host_floor_bytes":HOST_RESERVE,"guest_floor_bytes":GUEST_RESERVE,
              "snapshot_max_age_seconds":MIN_SNAPSHOT_AGE_SECONDS,"check_interval_seconds":5},
            "auth":"1000 exact-owned QA-preseeded DEV tenants; not1000 OAuth humans",
            "transport":"actual EventV2 WSS Agent processes; not SQLite records or HTTP health",
            "baseline_100_agent_rss_bytes":BASELINE_RAMP_RSS,
            "baseline_100_rss_times10_bytes":BASELINE_RAMP_RSS*10,
            "baseline_extrapolation_certifies_capacity":False,"budget":budget(mode),
            "cleanup":"stop exactPID+starttime+command+UID-owned processes; delete only exact journaled tenant/device IDs; validate zero rows and revoke credentials; remove only ownVM/runtime",
            "launch_prerequisites":["Root backend54 critical real tests closed","fresh host resource preflight",
              "own VM image SHA/UUID/MAC/key/knownhosts; guest source/hash preflight",
              "Services controller and isolatedVM Agent-manager transport smoke",
              "pin backend/Agent/testhelpers; safe Worker diagnostics and sanitized observer",
              "exact cleanup journal including partially created fixtures before mutation",
              "count application requests/D1commands and separate WSS/control/RPC/metrics traffic"],
            "agent_processes_launched":0,"bulk_load_started":False,
            "real_1000_short_passed":False,"real_1000_24h_passed":False,"real_72h_passed":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("short","soak24"),default="short")
    p.add_argument("--backend-version")
    p.add_argument("--collect-local",choices=("Services","Nucleo","Guest"))
    p.add_argument("--host-resources",type=Path)
    a=p.parse_args()
    if a.collect_local:
        print(json.dumps(local_resources(a.collect_local),sort_keys=True));return 0
    out=plan(a.mode,a.backend_version)
    app=Path(__file__).resolve().parents[1]
    out["source_sha256"]={s:hashlib.sha256((app/s).read_bytes()).hexdigest() for s in SOURCE_FILES}
    if a.host_resources:out["host_preflight"]=host_preflight(json.loads(a.host_resources.read_text()))
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    try:raise SystemExit(main())
    except ValueError as e:
        print(json.dumps({"state":"HOLD","code":str(e),"bulk_load_started":False}));raise SystemExit(1)
