#!/usr/bin/env python3
"""Verify an offline gate report against its exact revision and suite registry.

No cloud calls, credentials or deployment. This checks report consistency, not
cryptographic provenance: trusted execution and a clean checkout remain required.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

REGISTRY = Path(__file__).with_name('commander_prelaunch_offline_gate.py')
MAX_REPORT_BYTES = 1024 * 1024
SCOPE = 'LOCAL_ONLY_OFFLINE_NO_CLOUDFLARE_MUTATION'


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def registry_names(path: Path = REGISTRY) -> list[str]:
    """Read literal suite declarations without importing or executing the gate."""
    found = {}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('PYTHON', 'JS', 'MODELS'):
                    require(target.id not in found, 'CI_REGISTRY_DUPLICATE_DECLARATION')
                    found[target.id] = ast.literal_eval(node.value)
    require(set(found) == {'PYTHON', 'JS', 'MODELS'}, 'CI_REGISTRY_INCOMPLETE')
    names = []
    for group in ('PYTHON', 'JS', 'MODELS'):
        require(isinstance(found[group], (list, tuple)), 'CI_REGISTRY_INVALID_GROUP')
        names.extend(found[group])
    require(bool(names) and all(isinstance(n, str) and re.fullmatch(r'[A-Za-z0-9_]+\.(py|mjs)', n) for n in names), 'CI_REGISTRY_INVALID_NAME')
    require(len(names) == len(set(names)), 'CI_REGISTRY_DUPLICATE_TEST')
    return names


def load_report(path: Path) -> tuple[dict, str]:
    require(not path.is_symlink(), 'CI_REPORT_SYMLINK_DENIED')
    with path.open('rb') as handle:
        raw = handle.read(MAX_REPORT_BYTES + 1)
    require(0 < len(raw) <= MAX_REPORT_BYTES, 'CI_REPORT_SIZE_INVALID')
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'CI_REPORT_DUPLICATE_JSON_KEY')
            value[key] = item
        return value
    report = json.loads(raw, object_pairs_hook=pairs)
    require(isinstance(report, dict), 'CI_REPORT_OBJECT_REQUIRED')
    return report, hashlib.sha256(raw).hexdigest()


def verify_report(report: dict, expected_head: str, expected_tests: list[str], *,
                  stress: int = 1000, threads: int = 24,
                  now: datetime | None = None, max_age_seconds: int = 3600) -> dict:
    require(isinstance(report, dict), 'CI_REPORT_OBJECT_REQUIRED')
    require(isinstance(expected_head, str) and re.fullmatch(r'[0-9a-f]{40}', expected_head) is not None, 'CI_EXPECTED_HEAD_INVALID')
    require(bool(expected_tests) and len(set(expected_tests)) == len(expected_tests), 'CI_EXPECTED_SUITE_INVALID')
    require(report.get('schema') == 'hara.commander-prelaunch-offline-gate.v1', 'CI_REPORT_SCHEMA_INVALID')
    require(report.get('source_head') == expected_head, 'CI_REPORT_REVISION_MISMATCH')
    require(report.get('scope') == SCOPE, 'CI_REPORT_SCOPE_MISMATCH')
    for flag in ('production_rollout_authorized', 'real_multitenant_tested', 'real_cloudflare_1k_clients_tested'):
        require(report.get(flag) is False, 'CI_REPORT_UNSUPPORTED_CLAIM')
    for key, expected in [('checked', len(expected_tests)), ('passed', len(expected_tests)), ('failed', 0),
                          ('stress_attempts_per_scenario', stress), ('stress_threads', threads)]:
        require(type(report.get(key)) is int and report[key] == expected, 'CI_REPORT_COUNTER_MISMATCH')
    rows = report.get('tests')
    require(isinstance(rows, list) and len(rows) == len(expected_tests), 'CI_REPORT_SUITE_INCOMPLETE')
    require(all(isinstance(row, dict) for row in rows), 'CI_REPORT_ROW_INVALID')
    require([row.get('test') for row in rows] == expected_tests, 'CI_REPORT_SUITE_MISMATCH')
    for row in rows:
        require(row.get('state') == 'PASS' and type(row.get('exit_code')) is int and row['exit_code'] == 0
                and row.get('error') is None, 'CI_REPORT_TEST_NOT_PASS')
        seconds = row.get('seconds')
        require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0, 'CI_REPORT_DURATION_INVALID')
    try:
        at = datetime.fromisoformat(report['at_utc'].replace('Z', '+00:00'))
        require(at.utcoffset() is not None, 'CI_REPORT_TIME_INVALID')
        age = ((now or datetime.now(timezone.utc)) - at).total_seconds()
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ValueError('CI_REPORT_TIME_INVALID') from None
    require(-300 <= age <= max_age_seconds, 'CI_REPORT_TIME_OUTSIDE_WINDOW')
    return {'state': 'PASS', 'source_head': expected_head, 'validated_suites': len(rows),
            'scope': SCOPE, 'production_certified': False, 'real_client_capacity_certified': False,
            'report_age_seconds': round(age, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    try:
        report, digest = load_report(args.report)
        result = verify_report(report, args.expected_head, registry_names())
        result['report_sha256'] = digest
        print(json.dumps(result, sort_keys=True))
        if args.summary:
            # Only fixed messages, validated SHA and numeric counts enter Markdown.
            text = ('## Commander — regressão completa\n\n'
                    f'Commit: `{result["source_head"]}`\n\n'
                    f'Suítes aprovadas: **{result["validated_suites"]}**\n\n'
                    f'SHA-256 do relatório: `{digest}`\n\n'
                    'Teste offline; não certifica produção, custos ou clientes simultâneos.\n')
            with args.summary.open('a', encoding='utf-8') as handle:
                handle.write(text)
        return 0
    except (OSError, ValueError, SyntaxError, TypeError) as error:
        code = str(error)
        if not re.fullmatch(r'CI_[A-Z_]+', code):
            code = 'CI_REPORT_VALIDATION_FAILED'
        print(json.dumps({'state': 'FAIL', 'code': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
