#!/usr/bin/env python3
"""Offline evidence review, never an attestation or campaign admission.

The executor and independent Observer must authenticate these observations
outside this process. A consistent imported JSON cannot enable any runtime.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

METERS = ('worker_requests', 'worker_cpu_us', 'do_requests', 'do_active_gb_us',
          'do_storage_reads', 'do_storage_writes', 'do_storage_byte_seconds',
          'd1_rows_read', 'd1_rows_written', 'queue_billable_ops', 'dlq_billable_ops')
LIMITS = {'latency_p95_ms': 6000, 'latency_p99_ms': 12000,
          'detection_s': 180, 'recovery_s': 300}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def obj(value):
    return value if isinstance(value, dict) else {}


def integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', value))


def sha(value, size=64):
    return isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{'+str(size)+'}', value))


def validate_hosted_evidence(plan, evidence, now_ms):
    plan, evidence = obj(plan), obj(evidence)
    reasons, observed = [], {}
    def require(condition, code):
        if not condition and code not in reasons:
            reasons.append(code)
    for value in (plan, evidence):
        require(value.get('approved') in (None, False), 'FILE_APPROVAL_REJECTED')
    require(plan.get('schema') == 'hara.commander.r163.hosted-evidence-plan.v1'
            and evidence.get('schema') == 'hara.commander.r163.hosted-evidence.v1', 'SCHEMA_INVALID')
    require(plan.get('environment') == 'DEV' and identifier(plan.get('campaign_id'))
            and evidence.get('campaign_id') == plan.get('campaign_id'), 'CAMPAIGN_BINDING_INVALID')
    binding = obj(plan.get('binding'))
    require(binding == evidence.get('binding'), 'BINDING_MISMATCH')
    require(sha(binding.get('source_head'), 40) and binding.get('agent_version') == '0.3.56'
            and identifier(binding.get('worker_version')), 'SOURCE_VERSION_INVALID')
    resources, artifacts = obj(binding.get('resources')), obj(binding.get('artifacts_sha256'))
    require(set(resources) == {'account', 'worker', 'do_namespace', 'd1_database', 'queue', 'dlq', 'recipient'}
            and all(identifier(value) for value in resources.values()), 'RESOURCE_SCOPE_INVALID')
    require(set(artifacts) == {'linux_agent', 'windows_agent', 'worker', 'device_channel'}
            and all(sha(value) for value in artifacts.values())
            and sha(binding.get('query_sha256')) and sha(binding.get('rollback_sha256')), 'ARTIFACT_PIN_INVALID')
    window, limits = obj(plan.get('window')), obj(plan.get('limits'))
    start, end = window.get('from_ms'), window.get('to_ms')
    time_valid = all(integer(x) for x in (start, end, now_ms)) and start < end <= now_ms
    require(time_valid, 'CAMPAIGN_WINDOW_INVALID')
    require(set(limits) == set(LIMITS) and all(number(limits.get(k))
            and 0 < limits[k] <= bound for k, bound in LIMITS.items()), 'SLO_LIMITS_INVALID')
    target = plan.get('target_connections')
    require(type(target) is int and target in (500, 2000, 20000), 'RAMP_TARGET_INVALID')
    require(identifier(plan.get('executor_id')) and identifier(plan.get('observer_id'))
            and plan.get('executor_id') != plan.get('observer_id'), 'INDEPENDENT_OBSERVER_REQUIRED')
    points = []
    for role in ('executor', 'observer'):
        stream = obj(obj(evidence.get('live_wss')).get(role))
        require(stream.get('identity') == plan.get(role+'_id') and stream.get('kind') == 'LIVE_WSS', 'LIVE_WSS_PROVENANCE_REQUIRED')
        samples = stream.get('samples')
        good = isinstance(samples, list) and 0 < len(samples) <= 100000
        common, previous = set(), -1
        if good:
            for sample in samples:
                sample = obj(sample)
                at, count = sample.get('at_ms'), sample.get('live_connections')
                valid = integer(at) and integer(count) and time_valid and start <= at <= end and at > previous
                good = good and valid
                if valid and count == target:
                    common.add(at)
                if integer(at):
                    previous = at
        require(good and bool(common), 'LIVE_WSS_SAMPLES_INVALID')
        points.append(common)
    require(bool(points[0] & points[1]), 'INDEPENDENT_SIMULTANEITY_UNPROVEN')
    if points[0] & points[1]:
        observed['simultaneous_wss'] = target
    latency = evidence.get('latency_samples_ms')
    if isinstance(latency, list) and 0 < len(latency) <= 1000000 and all(number(x) for x in latency):
        ordered = sorted(latency)
        percentiles = {key: ordered[math.ceil(len(ordered)*p)-1] for key, p in (('p95_ms', .95), ('p99_ms', .99))}
        require(evidence.get('latency_summary') == percentiles, 'LATENCY_SUMMARY_MISMATCH')
        for key, value in percentiles.items():
            observed['latency_'+key] = value
            require(number(limits.get('latency_'+key)) and value <= limits['latency_'+key], 'LATENCY_SLO_EXCEEDED')
        observed['latency_sample_count'] = len(ordered)
    else:
        require(False, 'RAW_LATENCY_SAMPLES_REQUIRED')
    recoveries = evidence.get('recoveries')
    require(isinstance(recoveries, list) and 0 < len(recoveries) <= 100000, 'RECOVERY_OBSERVATIONS_REQUIRED')
    detection, recovery = [], []
    for row in recoveries if isinstance(recoveries, list) else []:
        row = obj(row)
        times = [row.get(k) for k in ('fault_at_ms', 'detected_at_ms', 'recovered_at_ms')]
        valid = identifier(row.get('device_id')) and all(integer(t) for t in times) and time_valid
        valid = valid and start <= times[0] <= times[1] <= times[2] <= end
        require(valid, 'RECOVERY_TIME_INVALID')
        if valid:
            detection.append((times[1]-times[0])/1000)
            recovery.append((times[2]-times[0])/1000)
    for key, values in (('detection', detection), ('recovery', recovery)):
        if values:
            observed['last_'+key+'_s'] = max(values)
            require(number(limits.get(key+'_s')) and max(values) <= limits[key+'_s'], 'RECOVERY_SLO_EXCEEDED')
    isolation = evidence.get('isolation_checks')
    require(isinstance(isolation, list) and bool(isolation), 'ISOLATION_PROOF_REQUIRED')
    for row in isolation if isinstance(isolation, list) else []:
        row = obj(row)
        require(identifier(row.get('request_tenant_id')) and identifier(row.get('resource_tenant_id'))
                and row['request_tenant_id'] != row['resource_tenant_id'] and row.get('http_status') in (403, 404)
                and type(row.get('effect_count')) is int and row['effect_count'] == 0, 'TENANT_ISOLATION_FAILED')
    receipts = evidence.get('durable_receipts')
    require(isinstance(receipts, list) and 0 < len(receipts) <= 100000, 'DURABLE_RECEIPTS_REQUIRED')
    seen = set()
    for row in receipts if isinstance(receipts, list) else []:
        row = obj(row)
        identity = {k: row.get(k) for k in ('tenant_id', 'device_id', 'call_id')}
        complete, replay = obj(row.get('complete')), obj(row.get('replay'))
        valid = all(identifier(x) for x in identity.values()) and obj(row.get('claim')) == identity
        valid = valid and all(complete.get(k) == v for k, v in identity.items())
        valid = valid and sha(row.get('fingerprint')) and complete.get('fingerprint') == row.get('fingerprint')
        valid = valid and identifier(complete.get('receipt_id')) and type(row.get('effect_count')) is int and row['effect_count'] == 1
        valid = valid and replay.get('existing') is True and replay.get('receipt_id') == complete.get('receipt_id')
        valid = valid and type(replay.get('additional_effects')) is int and replay['additional_effects'] == 0
        require(valid, 'DURABLE_RECEIPT_BINDING_FAILED')
        key = tuple(str(identity[k]) for k in identity)
        require(key not in seen, 'DURABLE_CALL_REPLAY_IN_EVIDENCE')
        seen.add(key)
    meter, close = obj(evidence.get('native_meter')), obj(evidence.get('post_close_receipt'))
    values = obj(meter.get('meters'))
    require(set(values) == set(METERS) and all(integer(x) for x in values.values()), 'NATIVE_METER_INCOMPLETE')
    require(meter.get('source_head') == binding.get('source_head') and meter.get('resources') == resources,
            'NATIVE_METER_SCOPE_MISMATCH')
    query = meter.get('query')
    require(isinstance(query, str) and hashlib.sha256(query.encode()).hexdigest() == binding.get('query_sha256')
            and meter.get('query_sha256') == binding.get('query_sha256'), 'NATIVE_METER_QUERY_MISMATCH')
    closed, captured, complete = close.get('closed_ms'), meter.get('captured_ms'), meter.get('complete_through_ms')
    readback = close.get('captured_ms')
    times = all(integer(t) for t in (closed, captured, complete, readback, now_ms)) and time_valid
    mw = obj(meter.get('window'))
    times = times and integer(mw.get('to_ms')) and mw.get('from_ms') == start
    times = times and end <= closed <= complete <= mw['to_ms'] <= captured <= readback <= now_ms
    times = times and now_ms-captured <= 60000
    require(times and identifier(close.get('receipt_id')) and type(close.get('open_wss')) is int
            and close['open_wss'] == 0, 'POST_CLOSE_METER_READBACK_REQUIRED')
    try:
        require(close.get('binding_sha256') == digest(binding)
                and close.get('native_capture_sha256') == digest(meter), 'POST_CLOSE_DIGEST_MISMATCH')
    except (ValueError, TypeError, RecursionError):
        require(False, 'POST_CLOSE_DIGEST_INVALID')
    return {'schema': 'hara.commander.r163.hosted-evidence-review.v1',
            'state': 'HOLD' if reasons else 'REVIEW_ONLY', 'reasons': reasons,
            'execute_allowed': False, 'native_acceptance': False, 'observed': observed,
            'claim': 'IMPORTED_OBSERVATIONS_REQUIRE_NATIVE_EXECUTOR_AND_INDEPENDENT_WITNESS'}


def read_json(path):
    source = Path(path)
    if source.stat().st_size > 32*1024*1024:
        raise ValueError('EVIDENCE_INPUT_TOO_LARGE')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('EVIDENCE_DUPLICATE_KEY')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('EVIDENCE_NONFINITE_NUMBER')
    return json.loads(source.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--now-ms', type=int, required=True)
    args = parser.parse_args()
    result = validate_hosted_evidence(read_json(args.plan), read_json(args.evidence), args.now_ms)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 2 if result['state'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
