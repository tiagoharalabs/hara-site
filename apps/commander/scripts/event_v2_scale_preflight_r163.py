#!/usr/bin/env python3
"""Offline ramp proposal and completed-checkpoint validator for #163.

No network, runtime writer, budget renewal, Queue resume, deployment or install.
Existing native budget/Queue enforcement stays in recovery_queue_budget_r163.mjs.
Caller-supplied counters are observations, never an admission or authority.
"""
import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

PROPOSED={'events':20000,'queue_ops':30000,'d1_reads':5000000,
          'd1_writes':1500000,'active_ms':360*60000}
METER_FIELDS={'reads_per_device','writes_per_device','reads_per_event','writes_per_event',
              'status_polls','reads_per_status','writes_per_status'}
LIMITS={'last_detection_s':180,'last_recovery_s':300,'latency_p95_ms':6000,'latency_p99_ms':12000}
ANOMALIES=('tenant_leaks','duplicate_effects','missing_receipts','retry_anomalies','dlq_unexpected')

def runtime_parity_map(app=None):
    """Source facts, not runtime authority or a commercial transport admission."""
    app=Path(app) if app else Path(__file__).resolve().parents[1]
    paths={'commercial_linux':'release-candidates/commercial-0.3.56-source/agent/linux.py',
           'commercial_windows':'release-candidates/commercial-0.3.56-source/agent/windows.ps1',
           'commercial_linux_driver':'release-candidates/commercial-0.3.56-source/agent/event_v2_dev.py',
           'commercial_linux_wire':'release-candidates/commercial-0.3.56-source/agent/event_v2_wire.py',
           'commercial_windows_driver':'release-candidates/commercial-0.3.56-source/agent/event_v2_dev.ps1',
           'commercial_windows_wire':'release-candidates/commercial-0.3.56-source/agent/event_v2_wire.ps1',
           'event_linux_loop':'experimental/event_v2_agent_loop.py',
           'event_linux_adapter':'experimental/event_v2_customer_agent.py',
           'event_windows_adapter':'experimental/event_v2_windows_agent.ps1',
           'worker':'src/worker.js','durable_object':'src/device-channel.mjs',
           'recovery_detector':'src/recovery-alerts.mjs','existing_qa_budget':'scripts/recovery_queue_budget_r163.mjs'}
    sources={};missing=[]
    for key,name in paths.items():
        p=app/name
        if not p.is_file():missing.append(name);continue
        raw=p.read_bytes();sources[key]={'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode()}
    def constant(source,name):
        if source not in sources:return None
        for node in ast.parse(sources[source]['text']).body:
            if isinstance(node,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in node.targets):
                try:return ast.literal_eval(node.value)
                except (ValueError,TypeError):return None
        return None
    def win_constant(name):
        match=re.search(r'^\$'+re.escape(name)+r'\s*=\s*(\d+)\s*$',sources.get('commercial_windows',{}).get('text',''),re.M)
        return int(match[1]) if match else None
    return {'claim_class':'SOURCE_MAP_WITH_FIXTURE_REFERENCES','state':'HOLD_AGENT_EVENT_V2_PARITY',
        'commercial_event_v2_parity':False,'missing_inputs':missing,
        'inputs':{key:{k:v for k,v in item.items() if k!='text'} for key,item in sources.items()},
        'commercial_0356':{
          'wake_transport':'EVENT_V2_DEV only when explicitly enabled',
          'durable_execution_transport':'OUTBOUND_RELAY authenticated claim/complete; existing journal/quota/receipt contract is unchanged',
          'linux':{'entry':'main -> run_supervised_relay','transport':'OUTBOUND_RELAY',
                   'version':constant('commercial_linux','AGENT_VERSION'),
                   'idle_poll_s':constant('commercial_linux','CALL_POLL_IDLE_SECONDS'),
                   'heartbeat_s':constant('commercial_linux','HEARTBEAT_SECONDS'),
                   'websocket_wiring':'DEV_SOURCE_WIRED_DEFAULT_OFF' if all(
                       key in sources for key in ('commercial_linux_driver','commercial_linux_wire'))
                       and 'def _event_v2_heartbeat_worker(' in sources.get('commercial_linux',{}).get('text','') else 'UNWIRED',
                   'dev_entry':'same .56 RelaySupervisor -> isolated Event V2 heartbeat + same journaled executor',
                   'dev_flag':'HARA_COMMANDER_EVENT_V2_DEV_ENABLED=true + exact DEV QA origin',
                   'dev_idle_claim_poll_s':None,'dev_probe_s':60,'dev_http_heartbeat_s':None},
          'windows':{'entry':'Start-WindowsRelaySupervisor -> heartbeat/executor/alerts',
                     'transport':'OUTBOUND_RELAY','idle_poll_s':win_constant('CallPollIdleSeconds'),
                     'heartbeat_s':win_constant('HeartbeatSeconds'),
                     'websocket_wiring':'DEV_SOURCE_WIRED_DEFAULT_OFF' if all(
                         key in sources for key in ('commercial_windows_driver','commercial_windows_wire'))
                         and 'function Start-WindowsEventV2Heartbeat(' in sources.get('commercial_windows',{}).get('text','') else 'UNWIRED',
                     'dev_flag':'boolean event_v2_dev_enabled=true + environment DEV + exact QA origin',
                     'dev_entry':'same .56 native Job Objects, private SID-scoped wake event and durable journal',
                     'dev_idle_claim_poll_s':None,'dev_probe_s':60,'dev_http_heartbeat_s':None}},
        'experimental_event_v2':{
          'linux':'event_v2_agent_loop -> event_v2_customer_agent -> public/agent/linux.py execution functions',
          'windows':'event_v2_windows_agent -> installed stable Agent functions; separate executable',
          'wake':'CALL_AVAILABLE -> bounded /api/device/calls/next -> execution -> /api/device/calls/complete',
          'authority':'Wake call_id is a hint; authenticated durable claim and correlated receipt fence effects.',
          'fallback':'Durable V1 claim/complete remains shared; failed Upgrade does not silently install or switch candidate transport.'},
        'worker_do':{'entry':'GET /api/device/channel -> openDeviceEventChannel -> tenant/device DeviceChannel',
                     'required':'Existing DEVICE_EVENT_V2_ENABLED + DEVICE_CHANNEL + enrollment; commercial protocol additionally requires exact DEV and DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED=true. This is not enabled by a source map.',
                     'presence':'connect/close/alarm fences and live enrollment checks remain in device-channel.mjs',
                     'recovery_event_v2':'DEV source uses independent hibernation probe timestamps and <=120s alarm, canonical SERVER persistence, lifecycle fences and same-incident RECOVERED. Native alarm/capacity/SLO acceptance remains HOLD.'},
        'p0_322':'Commercial journals/guardian, orphan reconciliation, Queue/DLQ and outbox are preserved. Source QA is not native #322 recovery/SLO acceptance.',
        'release_packaging':'HOLD: adjacent DEV helpers must be hashed and admitted in a new private source/release review; the original parity package and public installers are unchanged.',
        'native_windows':'VALK_240_PENDING','hosted_gate':'HOSTED_20K_HOLD','execute_allowed':False}

def integer(value):
    return type(value) is int and 0<=value<=2**53-1

def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def build_plan(*,stages=(500,2000,20000),proposed=None,metering=None,reconnect_limit_per_s=None):
    caps=dict(PROPOSED if proposed is None else proposed)
    if set(caps)!=set(PROPOSED) or any(not integer(v) or v==0 for v in caps.values()):
        raise ValueError('PREFLIGHT_PROPOSAL_INVALID')
    if tuple(stages)!=(500,2000,20000):raise ValueError('PREFLIGHT_RAMP_INVALID')
    if metering is not None and (not isinstance(metering,dict) or set(metering)!=METER_FIELDS
        or any(not integer(v) for v in metering.values())
        or not metering['reads_per_event'] or not metering['writes_per_event']):
        raise ValueError('PREFLIGHT_METERING_INVALID')
    if reconnect_limit_per_s is not None and (not number(reconnect_limit_per_s) or reconnect_limit_per_s==0):
        raise ValueError('PREFLIGHT_RECONNECT_LIMIT_INVALID')
    rows=[]
    for devices in stages:
        # Repeated completed cohorts, one incident + recovery per device. Warm
        # cohorts, retries and recoveries cannot disappear from cumulative caps.
        events=2*devices;scan=(devices+95)//96;delivery=(events+9)//10
        rows.append({'devices':devices,'events':events,'scan_jobs':scan,'delivery_jobs':delivery,
                     'queue_ops_upper':12*(scan+delivery)})
    totals={key:sum(row[key] for row in rows) for key in rows[0]}
    totals['d1_reads']=None if metering is None else (
        totals['devices']*metering['reads_per_device']+totals['events']*metering['reads_per_event']+
        metering['status_polls']*metering['reads_per_status'])
    totals['d1_writes']=None if metering is None else (
        totals['devices']*metering['writes_per_device']+totals['events']*metering['writes_per_event']+
        metering['status_polls']*metering['writes_per_status'])
    exceeded=[];unknown=[]
    for key,total in [('events',totals['events']),('queue_ops',totals['queue_ops_upper']),
                      ('d1_reads',totals['d1_reads']),('d1_writes',totals['d1_writes'])]:
        if total is None:unknown.append('UNBOUND_'+key.upper())
        elif total>caps[key]:exceeded.append('PROPOSED_'+key.upper()+'_EXCEEDED')
    if reconnect_limit_per_s is None:unknown.append('UNBOUND_RECONNECT_RATE')
    return {'schema':'hara.commander.r163.event-v2-scale-preflight.v1',
            'state':'HOLD_PLAN_BUDGET' if exceeded else 'HOLD_UNBOUND_LIMITS' if unknown else 'PLAN_REVIEW_READY',
            'proposed':caps,'approval_status':'NOT_APPROVED','stages':rows,'totals':totals,
            'metering':metering,'reconnect_limit_per_s':reconnect_limit_per_s,'limits':dict(LIMITS),
            'reasons':exceeded+unknown,'runtime_parity':'HOLD_AGENT_EVENT_V2_PARITY',
            'hosted_gate':'HOSTED_20K_HOLD','execute_allowed':False,
            'rollback':{'requested_operations':[
                'Stop the admitted load generator; preserve cumulative native counters and evidence.',
                'Native owner pauses affected DEV delivery using the existing canonical controls.',
                'Use the bound approved version/preimage; retain outboxes and receipt rows.'],
                'automatic_execution':False}}

def build_budget_alternatives(*, proposed=None, metering=None, reconnect_limit_per_s=None):
    """Two review scopes. Neither raises the smaller native QA lease/caps.

    Queue bounds include all warmup scans and 12 operations/job. Two events
    is a paired transport exercise, not the four-state #322 fault envelope.
    """
    import copy
    full = build_plan(proposed=proposed, metering=metering,
                      reconnect_limit_per_s=reconnect_limit_per_s)
    reduced = copy.deepcopy(full)
    for row in reduced['stages']:
        row['events'] = 20000 if row['devices'] == 20000 else 0
        row['delivery_jobs'] = (row['events'] + 9) // 10
        row['queue_ops_upper'] = 12 * (row['scan_jobs'] + row['delivery_jobs'])
    reduced['totals'] = {key: sum(row[key] for row in reduced['stages'])
                         for key in reduced['stages'][0]}
    for name, plan in [('full', full), ('reduced', reduced)]:
        events = plan['totals']['events']
        for kind in ('reads', 'writes'):
            plan['totals']['d1_' + kind] = None if metering is None else (
                22500 * metering[kind + '_per_device']
                + events * metering[kind + '_per_event']
                + metering['status_polls'] * metering[kind + '_per_status'])
        exceeded = []
        unknown = []
        for counter, total in [('events', events), ('queue_ops', plan['totals']['queue_ops_upper']),
                               ('d1_reads', plan['totals']['d1_reads']),
                               ('d1_writes', plan['totals']['d1_writes'])]:
            if total is None:
                unknown.append('UNBOUND_' + counter.upper())
            elif total > plan['proposed'][counter]:
                exceeded.append('PROPOSED_' + counter.upper() + '_EXCEEDED')
        if reconnect_limit_per_s is None:
            unknown.append('UNBOUND_RECONNECT_RATE')
        plan.update(cohort_mode='DISJOINT' if name == 'full' else 'NESTED_REUSED',
                    unique_devices=22500 if name == 'full' else 20000,
                    device_observations=22500, connection_target=20000,
                    recovery_selected_devices=22500 if name == 'full' else 10000,
                    recovery_events_per_device=2, requires_new_budget=bool(exceeded),
                    requires_native_admission=True,
                    full_20k_recovery_target=name == 'full',
                    full_20k_recovery_homologated=False,
                    metering_basis='UNBOUND' if metering is None else 'MODEL_FROM_SUPPLIED_UNIT_BOUNDS',
                    state='HOLD_PLAN_BUDGET' if exceeded else 'HOLD_UNBOUND_LIMITS' if unknown else 'PLAN_REVIEW_READY',
                    reasons=exceeded + unknown)
        # #322 can emit STALLED, RECOVERING, RECOVERED and DEGRADED. If all
        # four are generated, the paired-event proposal MUST be re-budgeted.
        upper_events = 4 * plan['recovery_selected_devices']
        upper_queue = 12 * (plan['totals']['scan_jobs'] + (upper_events + 9) // 10)
        plan['p0_322_four_state_envelope'] = {
            'events': upper_events, 'queue_ops_upper': upper_queue,
            'fits_proposed_events_and_queue': upper_events <= plan['proposed']['events']
                and upper_queue <= plan['proposed']['queue_ops'],
            'scope': 'Four state source recovery campaign requires its own explicit envelope.'}
        combined_events = 6 * plan['recovery_selected_devices']
        combined_queue = 12 * (plan['totals']['scan_jobs'] + (combined_events + 9) // 10)
        plan['p0_322_combined_envelope'] = {
            'guardian_workers_per_device': 1,
            'states_per_device_upper': 6, 'events': combined_events,
            'queue_ops_upper': combined_queue,
            'fits_proposed_events_and_queue': combined_events <= plan['proposed']['events']
                and combined_queue <= plan['proposed']['queue_ops'],
            'scope': 'One selected guardian worker, at most one emission per state, plus one SERVER pair. Additional transitions require STOP/re-budget; this is not an unlimited-incident bound.'}
        both_events = 10 * plan['recovery_selected_devices']
        both_queue = 12 * (plan['totals']['scan_jobs'] + (both_events + 9) // 10)
        plan['p0_322_both_guardians_envelope'] = {
            'guardian_workers_per_device': 2, 'state_emissions_per_worker': 4,
            'server_pairs_per_device': 1, 'states_per_device_upper': 10,
            'events': both_events, 'queue_ops_upper': both_queue,
            'fits_proposed_events_and_queue': both_events <= plan['proposed']['events']
                and both_queue <= plan['proposed']['queue_ops'],
            'scope': 'heartbeat and executor each emit up to four selected states, plus one SERVER pair. Further cycles/transitions stop and require explicit re-budget.'}
        plan['unit_rate_exposure'] = {
            'claim': 'PARTIAL_MODEL_BEFORE_ACCOUNT_ALLOWANCES_AND_ROUNDING',
            'queue_usd_equivalent': plan['totals']['queue_ops_upper'] * 0.40 / 1000000,
            'd1_usd_equivalent': None if metering is None else (
                plan['totals']['d1_reads'] * 0.001 + plan['totals']['d1_writes']) / 1000000,
            'total_usd': None,
            'excluded': ['Workers request/CPU, DO requests/duration/storage, sink, taxes, allocation and rounding.']}
    return {
        'schema': 'hara.commander.r163.event-v2-budget-alternatives.v1',
        'proposed': dict(full['proposed']), 'alternatives': {'full': full, 'reduced': reduced},
        'approval_status': 'NOT_APPROVED', 'hosted_gate': 'HOSTED_20K_HOLD',
        'execute_allowed': False,
        'native_budget_gaps': {
            'do_alarm_ops': True, 'do_storage_and_duration': True,
            'd1_alarm_lifecycle_reads': True,
            'detail': 'The current QA ledger caps D1/Queue/events/active time, not independent DO alarm/storage/duration. Include a lifecycle D1 lookup per alarm (healthy alarms have no D1 write). Owner must admit cumulative bounds and stop enforcement before enabling this DEV path.'},
        'pricing_reference': {
            'observed_on': '2026-10-25', 'account_allocation_verified': False,
            'usd_per_million': {'d1_reads': 0.001, 'd1_writes': 1.0,
                               'queue_ops': 0.40, 'do_requests': 0.15, 'do_gb_seconds': 12.50},
            'sources': ['https://developers.cloudflare.com/d1/platform/pricing/',
                        'https://developers.cloudflare.com/queues/platform/pricing/',
                        'https://developers.cloudflare.com/durable-objects/platform/pricing/'],
            'caveat': 'Published marginal unit rates, not an invoice or a cap approval. Account allowances, billing units and rounding must be resolved by owner.'},
        'measurements': {key: None for key in (
            'd1_reads', 'd1_writes', 'do_websocket_ops', 'do_alarm_ops',
            'do_connection_duration_ms', 'latency_p95_ms', 'latency_p99_ms',
            'last_detection_s', 'last_recovery_s')},
        'cost': {key: None for key in ('d1_usd', 'queue_usd', 'do_websocket_usd',
                                     'do_alarm_usd', 'do_connection_duration_usd', 'total_usd')},
        'remaining_bindings': [
            'Native Services QA budget/lease: previous 500 events / 4000 Queue caps are unchanged.',
            'Owner-approved throughput/concurrency, cumulative D1 unit bounds and stop controls.',
            'DO WebSocket message/connection/alarm/duration metering and applicable account pricing.',
            'Source .56 acceptance, Valk Windows #240 and independent Event V2 stale detector.',
            'p95/p99 and SLO 180s/300s must be measured; reconnect model is not hosted acceptance.']}


def evaluate_observation(plan,previous,current):
    """A completed stage checkpoint; in-flight reservations are not receipts.

    Feed next_checkpoint into the next evaluation. Its bounded cumulative receipt
    history prevents replay of an early cohort after the intermediate checkpoint.
    """
    reasons=[]
    def reject(code):
        if code not in reasons:reasons.append(code)
    if not isinstance(plan,dict) or plan.get('state')!='PLAN_REVIEW_READY':reject('PLAN_NOT_REVIEW_READY')
    caps=plan.get('proposed',{}) if isinstance(plan,dict) else {}
    if set(caps)!=set(PROPOSED) or any(not integer(v) for v in caps.values()):reject('PROPOSAL_INVALID')
    current=current if isinstance(current,dict) else {}
    previous=previous if isinstance(previous,dict) else ({} if previous is None else {'invalid':True})
    counters=current.get('counters');old=previous.get('counters',{})
    for key in PROPOSED:
        value=counters.get(key) if isinstance(counters,dict) else None
        before=old.get(key) if previous and isinstance(old,dict) else (None if previous else 0)
        if not integer(value) or not integer(before):reject('COUNTER_MISSING_OR_INVALID_'+key.upper());continue
        if value<before:reject('COUNTER_DECREASED_'+key.upper())
        if integer(caps.get(key)) and value>caps[key]:reject('BUDGET_EXCEEDED_'+key.upper())
    for key in ['active_connections','expected_connections',*ANOMALIES]:
        if not integer(current.get(key)):reject('METRIC_MISSING_OR_INVALID_'+key.upper())
    if current.get('active_connections')!=current.get('expected_connections'):reject('ACTIVE_CONNECTION_MISMATCH')
    if current.get('expected_connections') not in [500,2000,20000]:reject('RAMP_CHECKPOINT_INVALID')
    else:
        sizes=[row['devices'] for row in plan.get('stages',[])]
        index=sizes.index(current['expected_connections']) if current['expected_connections'] in sizes else -1
        prior_size=previous.get('expected_connections') if previous else None
        if index<0 or prior_size!=(None if index==0 else sizes[index-1]):reject('RAMP_ORDER_INVALID')
        if (isinstance(counters,dict) and index>=0 and
            counters.get('events')!=sum(row['events'] for row in plan['stages'][:index+1])):
            reject('RAMP_EVENT_COVERAGE_INCOMPLETE')
    if any(integer(current.get(key)) and current[key]>0 for key in ANOMALIES):reject('INTEGRITY_OR_RETRY_ANOMALY')
    for key,limit in LIMITS.items():
        if not number(current.get(key)):reject('METRIC_MISSING_OR_INVALID_'+key.upper())
        elif current[key]>limit:reject('SLO_EXCEEDED_'+key.upper())
    if (number(current.get('latency_p95_ms')) and number(current.get('latency_p99_ms'))
        and current['latency_p95_ms']>current['latency_p99_ms']):reject('LATENCY_PERCENTILES_INVERTED')
    rate=plan.get('reconnect_limit_per_s') if isinstance(plan,dict) else None
    peak=current.get('reconnect_peak_per_s')
    if not number(rate) or not rate or not number(peak):reject('RECONNECT_RATE_UNBOUND_OR_INVALID')
    elif peak>rate:reject('RECONNECT_RATE_EXCEEDED')
    receipts=current.get('receipts');prior=previous.get('receipt_history',previous.get('receipts',[]))
    before=old.get('events',0) if isinstance(old,dict) else None
    if previous and (not isinstance(prior,list) or not integer(before) or len(prior)!=before):
        reject('MISSING_CUMULATIVE_RECEIPT_HISTORY')
    seen={};history=[]
    def inspect(items,is_new):
        if not isinstance(items,list) or len(items)>50000:reject('RECEIPT_LIST_INVALID');return
        for row in items:
            if not isinstance(row,dict):reject('RECEIPT_INVALID');continue
            fields=['tenant_id','device_id','event_id','receipt_event_id','receipt_tenant_id','fingerprint','receipt_fingerprint']
            if any(not isinstance(row.get(k),str) or not row[k] or len(row[k])>180 for k in fields):
                reject('RECEIPT_BINDING_MISSING');continue
            if (row['event_id']!=row['receipt_event_id'] or row['tenant_id']!=row['receipt_tenant_id']
                or row['fingerprint']!=row['receipt_fingerprint']):reject('RECEIPT_BINDING_MISMATCH')
            if not re.fullmatch(r'HARA-REC-[0-9a-f]{48}',row['event_id']) or not re.fullmatch(r'[0-9a-f]{64}',row['fingerprint']):
                reject('RECEIPT_IDENTITY_INVALID')
            if row['event_id'] in seen:reject('EVENT_REPLAY_OR_PAYLOAD_CONFLICT')
            seen[row['event_id']]=(row['tenant_id'],row['device_id'],row['fingerprint']);history.append(dict(row))
    inspect(prior,False);inspect(receipts,True)
    count=counters.get('events') if isinstance(counters,dict) else None
    if (not isinstance(receipts,list) or not integer(count) or not integer(before)
        or len(receipts)!=count-before):reject('NEW_EVENT_RECEIPT_COUNT_MISMATCH')
    result={'state':'STOP' if reasons else 'CONTINUE_REVIEW_ONLY','reasons':reasons,
            'rollback_requested':bool(reasons),'execute_allowed':False,'hosted_gate':'HOSTED_20K_HOLD'}
    if not reasons:
        result['next_checkpoint']={**current,'receipt_history':history}
    return result

def read_json(path):
    p=Path(path)
    if p.stat().st_size>32*1024*1024:raise ValueError('PREFLIGHT_INPUT_TOO_LARGE')
    return json.loads(p.read_text())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposed');parser.add_argument('--metering')
    parser.add_argument('--reconnect-limit-per-s',type=float)
    parser.add_argument('--observation');parser.add_argument('--previous')
    parser.add_argument('--budget-alternatives', action='store_true')
    args=parser.parse_args()
    plan=build_plan(proposed=read_json(args.proposed) if args.proposed else None,
                    metering=read_json(args.metering) if args.metering else None,
                    reconnect_limit_per_s=args.reconnect_limit_per_s)
    output={'plan':plan,'runtime_map':runtime_parity_map()}
    if args.budget_alternatives:
        output['budget_alternatives']=build_budget_alternatives(
            proposed=plan['proposed'], metering=plan['metering'],
            reconnect_limit_per_s=args.reconnect_limit_per_s)
    if args.observation:output['observation']=evaluate_observation(plan,read_json(args.previous) if args.previous else None,read_json(args.observation))
    print(json.dumps(output,indent=2,sort_keys=True,allow_nan=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
