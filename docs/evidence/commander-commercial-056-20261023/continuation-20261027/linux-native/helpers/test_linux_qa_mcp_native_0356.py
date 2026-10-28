#!/usr/bin/env python3
"""Actual local MCP calls under the existing Ubuntu QA account, without mocks."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time

AGENT = Path('/home/commanderqa/.local/share/hara-commander/hara-commander-agent')
PIN = 'ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d'


def main():
    if os.getuid() != 2000 or hashlib.sha256(AGENT.read_bytes()).hexdigest() != PIN:
        raise RuntimeError('QA_IDENTITY_OR_ARTIFACT_MISMATCH')
    nonce = secrets.token_hex(20)
    expected = hashlib.sha256(nonce.encode()).hexdigest()
    program = 'import os,json,hashlib; n=' + repr(nonce) + '; print(json.dumps({"nonce":n,"uid":os.getuid(),"sha256":hashlib.sha256(n.encode()).hexdigest()}))'
    command = '/usr/bin/python3 -I -c ' + shlex.quote(program)
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-06-18', 'capabilities': {},
            'clientInfo': {'name': 'hara-native-qa', 'version': '0.3.56'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'get_config', 'arguments': {}}},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'get_device_info', 'arguments': {}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'start_process', 'arguments': {
            'command': command, 'timeout_ms': 5000, 'max_lines': 10}}},
    ]
    p = subprocess.Popen([sys.executable, '-I', str(AGENT), 'mcp'], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    started = time.monotonic()
    timed_out = False
    try:
        stdout, stderr = p.communicate(''.join(json.dumps(r) + '\n' for r in requests), timeout=25)
    except subprocess.TimeoutExpired:
        timed_out = True
        p.kill()
        stdout, stderr = p.communicate(timeout=5)
    responses = [json.loads(line) for line in stdout.splitlines() if line.strip().startswith('{')]
    calls = []
    for response in responses:
        if response.get('id') not in (2, 3, 4):
            continue
        result = response.get('result') or {}
        body = result.get('structuredContent')
        if body is None:
            texts = [c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text']
            try:
                body = json.loads('\n'.join(texts))
            except ValueError:
                body = {'unparsed_text': '\n'.join(texts)[:2500]}
        calls.append({'id': response['id'], 'jsonrpc_error': response.get('error'),
                      'is_error': result.get('isError', False), 'body': body})
    report = {'schema': 'hara.commander.qa-linux-local-mcp.v1',
              'state': 'CAPTURED_NATIVE_LOCAL_MCP_REQUIRES_RESULT_VALIDATION',
              'uid': os.getuid(), 'agent_sha256': PIN, 'nonce': nonce,
              'expected_payload_sha256': expected, 'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
              'mcp_exit': p.returncode, 'timed_out': timed_out,
              'duration_seconds': round(time.monotonic() - started, 3),
              'stderr_bytes': len(stderr.encode()), 'stderr_sha256': hashlib.sha256(stderr.encode()).hexdigest(),
              'calls': calls, 'cloud_mcp_e2e_proven': False}
    print(json.dumps(report, separators=(',', ':')))
    return 7 if timed_out or p.returncode != 0 else 0


if __name__ == '__main__':
    raise SystemExit(main())
