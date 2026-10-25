#!/usr/bin/env python3
"""Offline cumulative financial proposal. No account access or runtime authority.

Prices and billing units must be supplied by the financial owner. A complete
model is still NOT_APPROVED; actual cost and provider completeness stay unknown.
"""
import argparse
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from event_v2_hosted_evidence_r163 import METERS
from event_v2_scale_preflight_r163 import build_budget_alternatives

RESOURCE_FIELDS = {'account_id', 'worker', 'worker_version', 'do_namespace',
                   'd1_database', 'queue', 'dlq', 'recipient', 'cohort_sha256'}
STOP_FIELDS = {'owner', 'executor_ref', 'stop_ref', 'rollback_version',
               'rollback_sha256', 'concurrency_limit', 'reconnect_limit_per_s', 'active_ms'}
RATE_FIELDS = {'usd_per_unit', 'reference', 'billing_unit', 'rounding_units'}
MAX_INTEGER = 2**53 - 1
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
UNKNOWN = {'UNKNOWN', 'TBD', 'PENDING', 'UNBOUND', 'NONE', 'NULL', 'N/A'}


def positive_integer(value):
    return type(value) is int and 0 < value <= MAX_INTEGER


def reference(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        return False
    if value.upper() in UNKNOWN:
        return False
    if any(c.isspace() or ord(c) < 32 for c in value):
        return False
    if re.search(r'(?i)(bearer|token=|password=|secret=|api_key=)', value):
        return False
    try:
        parsed = urlsplit(value)
        return not (parsed.username or parsed.password or parsed.query or parsed.fragment)
    except ValueError:
        return False


def positive_decimal(value):
    # Bound both precision and magnitude; Decimal must not amplify arbitrary
    # exponent strings or round a financial maximum down in its default context.
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,16}(?:\.\d{1,24})?', value):
        return None
    try:
        number = Decimal(value)
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def build_decision(source_head, *, alternative='A', max_total_usd='5.00',
                   caps=None, pricing=None, resources=None, stop=None):
    if alternative not in ('A', 'B'):
        raise ValueError('UNKNOWN_CAMPAIGN_ALTERNATIVE')
    reasons = []
    ceiling = positive_decimal(max_total_usd)
    if ceiling is None:
        reasons.append('UNBOUND_FINANCIAL_CEILING')
    if not isinstance(source_head, str) or not re.fullmatch('[0-9a-f]{40}', source_head):
        reasons.append('UNBOUND_SOURCE_HEAD')
    valid_caps = (isinstance(caps, dict) and set(caps) == set(METERS)
                  and all(positive_integer(v) for v in caps.values()))
    if not valid_caps:
        reasons.append('UNBOUND_CUMULATIVE_CAPS')
    valid_rates = isinstance(pricing, dict) and set(pricing) == set(METERS)
    if valid_rates:
        for row in pricing.values():
            if not isinstance(row, dict) or set(row) != RATE_FIELDS:
                valid_rates = False
                break
            url = urlsplit(row['reference']) if reference(row['reference']) else None
            if (positive_decimal(row['usd_per_unit']) is None
                    or not positive_integer(row['rounding_units'])
                    or not reference(row['billing_unit']) or url is None
                    or url.scheme != 'https' or url.netloc != 'developers.cloudflare.com'
                    or not url.path.endswith('/pricing/')):
                valid_rates = False
                break
    if not valid_rates:
        reasons.append('UNBOUND_ALL_COMPONENT_PRICING')
    valid_resources = (isinstance(resources, dict) and set(resources) == RESOURCE_FIELDS
                       and all(reference(v) for v in resources.values()))
    if valid_resources:
        valid_resources = bool(re.fullmatch('[0-9a-f]{32}', resources['account_id'])
                               and re.fullmatch('[0-9a-f]{32}', resources['do_namespace'])
                               and UUID.fullmatch(resources['worker_version'])
                               and UUID.fullmatch(resources['d1_database'])
                               and re.fullmatch('[0-9a-f]{64}', resources['cohort_sha256']))
    if not valid_resources:
        reasons.append('UNBOUND_ISOLATED_NATIVE_RESOURCES')
    number_fields = {'concurrency_limit', 'reconnect_limit_per_s', 'active_ms'}
    valid_stop = (isinstance(stop, dict) and set(stop) == STOP_FIELDS
                  and all(positive_integer(stop[k]) if k in number_fields else reference(stop[k])
                          for k in STOP_FIELDS))
    if valid_stop:
        valid_stop = (bool(re.fullmatch('[0-9a-f]{64}', stop['rollback_sha256']))
                      and bool(UUID.fullmatch(stop['rollback_version']))
                      and stop['concurrency_limit'] <= 64
                      and stop['active_ms'] <= 6 * 60 * 60 * 1000)
    if not valid_stop:
        reasons.append('UNBOUND_OWNER_STOP_ROLLBACK')
    plans = build_budget_alternatives(
        reconnect_limit_per_s=stop['reconnect_limit_per_s'] if valid_stop else None)
    campaign = plans['alternatives']['full' if alternative == 'A' else 'reduced']
    totals = {meter: None for meter in METERS}
    modeled = None
    # Unknown identities, prices or stop references do not become free usage.
    if not reasons:
        with localcontext() as context:
            context.prec = 96
            for meter in METERS:
                quantum = pricing[meter]['rounding_units']
                units = ((caps[meter] + quantum - 1) // quantum) * quantum
                totals[meter] = format(Decimal(units) * Decimal(pricing[meter]['usd_per_unit']), 'f')
            total = sum((Decimal(v) for v in totals.values()), Decimal(0))
            modeled = format(total, 'f')
            if total > ceiling:
                reasons.append('MODELED_MAX_EXCEEDS_FINANCIAL_CEILING')
        if caps['queue_billable_ops'] < campaign['totals']['queue_ops_upper']:
            reasons.append('CUMULATIVE_QUEUE_CAP_BELOW_CAMPAIGN')
        # Status observation itself is paid work, separate from load traffic.
        if caps['do_requests'] < 22500 or caps['d1_rows_read'] < 22500:
            reasons.append('COHORT_OBSERVER_CAP_BELOW_ONE_READ_PER_OBSERVATION')
    return {
        'schema': 'hara.commander.r163.campaign-financial-decision.v1',
        'state': 'HOLD' if reasons else 'REVIEW_ONLY', 'alternative': alternative,
        'source_head': source_head if 'UNBOUND_SOURCE_HEAD' not in reasons else None,
        'max_total_usd': max_total_usd if ceiling is not None else None,
        'modeled_max_usd': modeled, 'modeled_by_meter_usd': totals,
        'actual_cost_usd': None, 'campaign': campaign,
        'caps': caps if valid_caps else None, 'pricing': pricing if valid_rates else None,
        'resources': resources if valid_resources else None, 'stop': stop if valid_stop else None,
        'cohort_observer_reads_hint': 22500,
        'observer_overhead_scope': 'LOWER_BOUND_ONE_DO_STATUS_AND_LIFECYCLE_READ_PER_OBSERVATION; '
                                   'CPU_STORAGE_SUBREQUESTS_AND_REPEATED_SNAPSHOTS_REQUIRE_NATIVE_BOUNDS',
        'reasons': reasons, 'approval_status': 'NOT_APPROVED',
        'hosted_gate': 'HOSTED_20K_HOLD', 'execute_allowed': False,
        'required_native_gates': ['OWNER_FINANCIAL_APPROVAL', 'COMPLETE_PROVIDER_WATERMARK',
                                  'NATIVE_WSS_METER', 'INDEPENDENT_WSS_ATTESTATION',
                                  'PINNED_STOP_ROLLBACK_AND_ISOLATED_RESOURCES'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-head', required=True)
    parser.add_argument('--alternative', choices=('A', 'B'), default='A')
    parser.add_argument('--max-total-usd', default='5.00', help='Proposed ceiling, never permission.')
    parser.add_argument('--inputs', type=Path, help='Optional non-secret owner review references and bounds.')
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text()) if args.inputs else {}
    if not isinstance(inputs, dict) or set(inputs) - {'caps', 'pricing', 'resources', 'stop'}:
        parser.error('Only non-secret caps/pricing/resources/stop proposal fields are accepted.')
    print(json.dumps(build_decision(args.source_head, alternative=args.alternative,
                                  max_total_usd=args.max_total_usd, **inputs),
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
