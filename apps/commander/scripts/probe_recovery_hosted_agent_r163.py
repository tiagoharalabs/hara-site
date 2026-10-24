"""Explicit Services QA only; imports the Agent, never installs or starts it.

Credential bytes stay in the authorized executor. New private campaign required;
the original hosted evidence, device enrollment and public artifacts are untouched.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import urllib.error
from unittest.mock import patch


ROOT = Path('/tmp/hara-cmd163-hosted-qa-20261024')
ORIGIN = 'https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev'


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def private_file(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_mode & 0o077 == 0, 'QA_PROTECTED_FILE_REQUIRED')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--agent-source', type=Path, required=True)
    parser.add_argument('--agent-sha256', required=True)
    args = parser.parse_args()
    campaign = args.campaign
    require(campaign.parent == ROOT and campaign.name.startswith('codex-r163-integration-')
            and not campaign.is_symlink() and campaign.is_dir()
            and campaign.stat().st_mode & 0o077 == 0, 'QA_CAMPAIGN_NOT_PRIVATE')
    require(args.agent_source.is_relative_to(campaign), 'QA_SOURCE_OUTSIDE_CAMPAIGN')
    source_sha = hashlib.sha256(args.agent_source.read_bytes()).hexdigest()
    require(source_sha == args.agent_sha256, 'QA_SOURCE_SHA_MISMATCH')
    protected = ROOT / 'device.token'
    private_file(protected)
    original = json.loads((campaign / 'preflight-public.json').read_text())['original_evidence']
    require(all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                for name, digest in original.items()), 'ORIGINAL_EVIDENCE_CHANGED')
    spec = importlib.util.spec_from_file_location('hara_r163_qa_agent', args.agent_source)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    agent.DATA_DIR = campaign / 'agent-state'
    config = {'HARA_COMMANDER_URL': ORIGIN, 'HARA_DEVICE_ID': 'HARA-DEV-RECOVERY-163',
              'HARA_DEVICE_TOKEN': protected.read_text().strip()}
    outbox = agent.RecoveryEventOutbox(config)
    events = [outbox.enqueue('executor', state)
              for state in ('STALLED', 'RECOVERING', 'DEGRADED', 'RECOVERED')]
    require(len({e['event_id'] for e in events}) == 4, 'QA_NEW_IDS_REQUIRED')
    now = int(time.time() * 1000)
    # Controlled local unavailability, never a real Services/Storage fault.
    with patch.object(agent, 'post_json', side_effect=TimeoutError('SYNTHETIC_QA_OUTAGE')):
        require(outbox.send_once(now_ms=now)['state'] == 'RETRY', 'QA_RETRY_ABSENT')
    outbox = agent.RecoveryEventOutbox(config)
    for _ in events:
        require(outbox.send_once(now_ms=now + 10000)['state'] == 'PERSISTED', 'QA_INGEST_NOT_PERSISTED')
    with patch.object(agent, 'post_json', side_effect=RuntimeError('MUST_NOT_REPLAY')) as send:
        require(outbox.send_once(now_ms=now + 20000)['state'] == 'EMPTY', 'QA_PERSISTED_REPLAY')
        require(send.call_count == 0, 'QA_PERSISTED_SEND_ATTEMPT')
    duplicate = agent.post_json(ORIGIN + '/api/device/recovery-events',
                               config['HARA_DEVICE_TOKEN'], events[0], timeout=5)
    require(duplicate['duplicate'] is True and duplicate['ack'] == 'PERSISTED', 'QA_DUPLICATE_NOT_IDEMPOTENT')
    for label, token, event, expected in [
        ('no_auth', '', events[0], 401),
        ('conflict', config['HARA_DEVICE_TOKEN'], {**events[0], 'state': 'RECOVERED'}, 409),
    ]:
        try:
            agent.post_json(ORIGIN + '/api/device/recovery-events', token, event, timeout=5)
        except urllib.error.HTTPError as exc:
            require(exc.code == expected, 'QA_NEGATIVE_' + label)
        else:
            raise RuntimeError('QA_NEGATIVE_ACCEPTED_' + label)
    with sqlite3.connect(outbox.path) as db:
        rows = db.execute('SELECT event_id,server_event_id,state,attempts FROM recovery_events ORDER BY sequence').fetchall()
    require(len(rows) == 4 and all(r[2] == 'PERSISTED' for r in rows), 'QA_STORE_NOT_PERSISTED')
    evidence = {'schema': 'hara.commander.r163.hosted-agent.v1', 'state': 'PASS',
                'origin': ORIGIN, 'source_sha256': source_sha, 'credential_values_exported': False,
                'agent_installed': False, 'production_modified': False, 'new_sqlite': str(outbox.path),
                'outage_injection': 'LOCAL_TRANSPORT_ONLY', 'retry_after_restart': True,
                'persisted_events_never_resent': True, 'idempotency_and_conflict_passed': True,
                'events': [{'event': event, 'server_event_id': row[1], 'state': row[2], 'attempts': row[3]}
                           for event, row in zip(events, rows)]}
    with (campaign / 'hosted-agent-evidence.json').open('x', encoding='utf-8') as stream:
        os.chmod(stream.name, 0o600)
        stream.write(json.dumps(evidence, indent=2) + '\n')
    require(all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                for name, digest in original.items()), 'ORIGINAL_EVIDENCE_CHANGED')
    print(json.dumps({'state': 'PASS_HOSTED_REAL_AGENT_OUTBOX', 'events': len(rows),
                      'source_sha256': source_sha, 'campaign': str(campaign)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not print request objects, credential data or exception messages.
        print(json.dumps({'state': 'FAIL_HOSTED_AGENT_PROBE', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
