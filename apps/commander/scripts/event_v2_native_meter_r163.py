#!/usr/bin/env python3
"""Validate imported Cloudflare GraphQL exports for #163, entirely offline.

The query hash/variables, resources and source HEAD must be pinned by the
reviewer separately from each export. JSON metadata does not attest a network
response or grant execution authority. Only documented provider fields are
read; absent datasets/fields are unknown, including duration or storage
operations not supported here. Analytics can lag and cannot replace the
existing reserve-before-effect budget. No credential, network or writer API.
Policy variables contain the reviewed resource/account filters. The request
adds start/end epoch seconds for the fixed-start cumulative window; the pinned
query must consume those variables. rows_complete is an export completeness
claim for review, not authenticated pagination or provider provenance.

Provider references (verified 2026-10-25):
https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/
https://developers.cloudflare.com/d1/observability/metrics-analytics/
https://developers.cloudflare.com/queues/observability/metrics/
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time


POLICY_SCHEMA = 'hara.commander.r163.native-meter-policy.v1'
CAPTURE_SCHEMA = 'hara.commander.r163.native-meter-capture.v1'
MAX_BYTES = 32 * 1024 * 1024
# requests are raw requests, not billable 20:1 WebSocket units. Alarm
# invocations are already included: do not add a second alarm cost to this.
# storedBytes is a gauge: query must aggregate the bound namespace and group
# only by time; never sum samples of the same storage across polling windows.
FIELDS = {
    'do_requests': ('durableObjectsInvocationsAdaptiveGroups', 'sum', 'requests', 'count'),
    'do_storage_bytes': ('durableObjectsStorageGroups', 'max', 'storedBytes', 'bytes'),
    'd1_reads': ('d1AnalyticsAdaptiveGroups', 'sum', 'rowsRead', 'rows'),
    'd1_writes': ('d1AnalyticsAdaptiveGroups', 'sum', 'rowsWritten', 'rows'),
    'queue_ops': ('queueMessageOperationsAdaptiveGroups', 'sum', 'billableOperations', 'operations'),
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _number(value):
    return ((type(value) is int and 0 <= value <= 2**53 - 1)
            or (type(value) is float and math.isfinite(value) and 0 <= value <= 2**53 - 1))


def _integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def _duplicate_guard(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('NATIVE_JSON_DUPLICATE_KEY')
        result[key] = value
    return result


def parse_json(raw):
    if not isinstance(raw, str) or len(raw.encode()) > MAX_BYTES:
        raise ValueError('NATIVE_INPUT_TOO_LARGE_OR_INVALID')
    def bad_constant(_):
        raise ValueError('NATIVE_JSON_NONFINITE')
    return json.loads(raw, object_pairs_hook=_duplicate_guard, parse_constant=bad_constant)


def read_json(path):
    source = Path(path)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('NATIVE_INPUT_TOO_LARGE_OR_INVALID')
    return parse_json(source.read_text(encoding='utf-8'))


def evaluate_native_meter(policy, capture, previous=None, *, now=None):
    """Review one fixed-start cumulative export; never sum overlapping polls.

    The raw response is retained by the caller. This result pins its digest and
    the reviewed query, not an assertion that a provider request occurred.
    Counter decreases fail closed; a gauge may decrease but its conservative
    high-water exposure cannot erase earlier storage use.
    """
    reasons = []
    def reject(code):
        if code not in reasons:
            reasons.append(code)
    result = {
        'schema': 'hara.commander.r163.native-meter-result.v1',
        'state': 'STOP', 'reasons': reasons, 'observed': {},
        'claim': 'IMPORTED_PROVIDER_EXPORT_NOT_NATIVE_ADMISSION',
        'execute_allowed': False, 'hosted_gate': 'HOSTED_20K_HOLD',
        'total_cost_usd': None,
        'cost_note': 'Raw DO requests are not weighted billing units; allowances, '
                     'rounding, duration and storage operations are not inferred.',
        'websocket_note': 'Provider connection metrics arrive after close; this '
                          'export does not prove simultaneous live sockets.',
        'coverage': 'Only dimensions explicitly bounded by this policy are evaluated; '
                    'this is not complete provider billing or a campaign admission.',
    }
    if not isinstance(policy, dict) or not isinstance(capture, dict):
        reject('NATIVE_POLICY_OR_CAPTURE_INVALID')
        return result
    if policy.get('schema') != POLICY_SCHEMA or capture.get('schema') != CAPTURE_SCHEMA:
        reject('NATIVE_SCHEMA_INVALID')
    if policy.get('approved') is True or capture.get('approved') is True:
        reject('NATIVE_FILE_APPROVAL_REJECTED')
    if not re.fullmatch('[0-9a-f]{40}', str(policy.get('source_head', ''))):
        reject('NATIVE_SOURCE_HEAD_INVALID')
    if capture.get('source_head') != policy.get('source_head'):
        reject('NATIVE_SOURCE_HEAD_MISMATCH')
    if not re.fullmatch('[0-9a-f]{32}', str(policy.get('account_id', ''))):
        reject('NATIVE_ACCOUNT_INVALID')
    resources = policy.get('resources')
    if not isinstance(resources, dict) or not resources or capture.get('resources') != resources:
        reject('NATIVE_RESOURCE_IDENTITY_MISMATCH')
    limits = policy.get('limits')
    if not isinstance(limits, dict) or not limits or any(
            not isinstance(key, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', key)
            or not _number(value) or value <= 0 for key, value in (limits or {}).items()):
        reject('NATIVE_LIMITS_INVALID')
        limits = {}
    request = capture.get('request')
    query = request.get('query') if isinstance(request, dict) else None
    query_digest = hashlib.sha256(query.encode()).hexdigest() if isinstance(query, str) else None
    if not re.fullmatch('[0-9a-f]{64}', str(policy.get('query_sha256', ''))) or query_digest != policy.get('query_sha256'):
        reject('NATIVE_QUERY_PIN_MISMATCH')
    variables = policy.get('variables')
    expected_variables = ({**variables, 'start': capture.get('window_start'),
                           'end': capture.get('window_end')} if isinstance(variables, dict) else None)
    if (not isinstance(variables, dict) or 'start' in variables or 'end' in variables
            or variables.get('accountTag') != policy.get('account_id')
            or not isinstance(request, dict) or request.get('variables') != expected_variables):
        reject('NATIVE_QUERY_VARIABLES_MISMATCH')
    start, end, captured = (capture.get(key) for key in ('window_start', 'window_end', 'captured_at'))
    clock = int(time.time()) if now is None else now
    age, lag = policy.get('max_age_seconds'), policy.get('max_ingestion_lag_seconds')
    if (not all(_integer(value) for value in (start, end, captured, clock, age, lag))
            or age == 0 or lag == 0 or age > 86400 or lag > 86400):
        reject('NATIVE_TIME_POLICY_INVALID')
    else:
        if start != policy.get('window_start'):
            reject('NATIVE_BASELINE_MISMATCH')
        if not start < end <= captured <= clock:
            reject('NATIVE_TIME_ORDER_INVALID')
        if clock - captured > age:
            reject('NATIVE_EXPORT_STALE')
        if captured - end > lag:
            reject('NATIVE_INGESTION_LAG_EXCEEDED')
    if capture.get('rows_complete') is not True:
        reject('NATIVE_ROWS_INCOMPLETE')
    response = capture.get('response')
    try:
        raw_digest = hashlib.sha256(_canonical(response)).hexdigest()
        policy_digest = hashlib.sha256(_canonical(policy)).hexdigest()
    except (ValueError, TypeError, OverflowError, RecursionError):
        reject('NATIVE_JSON_NONFINITE_OR_INVALID')
        raw_digest = policy_digest = None
    result.update(raw_response_sha256=raw_digest, policy_sha256=policy_digest,
                  query_sha256=query_digest)
    if not isinstance(response, dict) or response.get('errors'):
        reject('NATIVE_PROVIDER_RESPONSE_ERROR')
    try:
        accounts = response['data']['viewer']['accounts']
        if not isinstance(accounts, list) or len(accounts) != 1 or accounts[0].get('accountTag') != policy.get('account_id'):
            raise ValueError()
        account = accounts[0]
    except (KeyError, TypeError, AttributeError, ValueError):
        reject('NATIVE_RESPONSE_ACCOUNT_MISMATCH')
        account = {}
    prior = {} if previous is None else previous
    if not isinstance(prior, dict):
        reject('NATIVE_PREVIOUS_CHECKPOINT_INVALID')
        prior = {}
    if previous is not None:
        if prior.get('policy_sha256') != policy_digest or prior.get('window_start') != start:
            reject('NATIVE_PREVIOUS_IDENTITY_MISMATCH')
        if not _integer(prior.get('window_end')) or not _integer(end) or end < prior['window_end']:
            reject('NATIVE_WINDOW_REGRESSED')
    observed, high_water = result['observed'], {}
    for metric, limit in limits.items():
        definition = FIELDS.get(metric)
        observed[metric] = None
        if definition is None:
            reject('NATIVE_METRIC_UNAVAILABLE_' + metric.upper())
            continue
        dataset, aggregation, field, unit = definition
        rows = account.get(dataset)
        if not isinstance(rows, list) or not rows or len(rows) > 10000:
            reject('NATIVE_DATASET_UNAVAILABLE_' + metric.upper())
            continue
        values = []
        for row in rows:
            group = row.get(aggregation) if isinstance(row, dict) else None
            value = group.get(field) if isinstance(group, dict) else None
            if not _number(value):
                reject('NATIVE_METRIC_INVALID_' + metric.upper())
                break
            values.append(value)
        if len(values) != len(rows):
            continue
        value = max(values) if aggregation == 'max' else sum(values)
        if not _number(value):
            reject('NATIVE_METRIC_INVALID_' + metric.upper())
            continue
        observed[metric] = value
        before = prior.get('observed', {}).get(metric) if isinstance(prior.get('observed', {}), dict) else None
        old_high = prior.get('high_water', {}).get(metric) if isinstance(prior.get('high_water', {}), dict) else None
        if previous is not None and (not _number(before) or not _number(old_high)):
            reject('NATIVE_PREVIOUS_METRIC_MISSING_' + metric.upper())
        elif _number(before) and old_high < before:
            reject('NATIVE_PREVIOUS_HIGH_WATER_INVALID_' + metric.upper())
        if aggregation != 'max' and _number(before) and value < before:
            reject('NATIVE_COUNTER_DECREASED_' + metric.upper())
        high_water[metric] = max(value, old_high) if _number(old_high) else value
        if high_water[metric] > limit:
            reject('NATIVE_BUDGET_EXCEEDED_' + metric.upper())
    result['units'] = {key: FIELDS[key][3] for key in limits if key in FIELDS}
    if not reasons:
        result['state'] = 'CONTINUE_REVIEW_ONLY'
        result['next_checkpoint'] = {
            'policy_sha256': policy_digest, 'raw_response_sha256': raw_digest,
            'window_start': start, 'window_end': end,
            'observed': dict(observed), 'high_water': high_water,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--previous')
    args = parser.parse_args()
    try:
        result = evaluate_native_meter(read_json(args.policy), read_json(args.capture),
                                       read_json(args.previous) if args.previous else None)
    except (OSError, ValueError, TypeError):
        result = {'state': 'STOP', 'reasons': ['NATIVE_INPUT_INVALID'], 'execute_allowed': False}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result['state'] == 'CONTINUE_REVIEW_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
