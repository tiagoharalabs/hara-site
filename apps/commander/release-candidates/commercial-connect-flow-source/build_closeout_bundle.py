#!/usr/bin/env python3
"""Build an explicit, pinned local delivery bundle; never access Git or a host.

The envelope matches the previous git-delivery.json transport: destination path
maps to bytes, sha256 and base64(zlib(data)). The root operator independently
checks the resulting bundle hash and repository preimage before applying it.
This helper does not stage, commit, push, install, or publish anything.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zlib


SOURCE_ROOT = Path(__file__).resolve().parent
ALLOWLIST_NAME = 'closeout-file-allowlist.json'
PREFIXES = (
    'apps/commander/release-candidates/commercial-connect-flow-source/',
    'docs/evidence/commander-commercial-056-20261023/continuation-20261027/connect-flow-20261028/',
)
ALLOWLIST_DESTINATION = PREFIXES[0] + ALLOWLIST_NAME
MAX_FILE_BYTES = 700_000
MAX_TOTAL_BYTES = 8_000_000
MAX_ENTRIES = 180
HASH = re.compile(r'[0-9a-f]{64}')
EXTENSIONS = {'.py', '.ps1', '.sh', '.patch', '.md', '.json', '.jwk'}
PRIVATE_NAMES = {
    'device.env', 'device.json', 'config.before.private', 'credentials.json',
    'release-signing-private.jwk', 'release-metadata-transfer.json',
    'git-delivery.json', 'closeout-git-delivery.json',
}
SENSITIVE_JSON_KEYS = {
    'access_token', 'refresh_token', 'id_token', 'pairing_token', 'device_token',
    'client_secret', 'password', 'cookie', 'cookies', 'private_key', 'private_jwk',
    'authorization_header', 'device_credential', 'encrypted_device_token',
}


def need(condition, code):
    if not condition:
        raise ValueError(code)


def relative_path(value):
    need(isinstance(value, str) and value and '\\' not in value, 'RELATIVE_POSIX_PATH_REQUIRED')
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value, 'NORMALIZED_RELATIVE_PATH_REQUIRED')
    need(all(part not in ('.', '..') and not part.startswith('.')
             for part in path.parts), 'PATH_COMPONENT_REFUSED')
    need(not any(part in ('__pycache__', 'node_modules') for part in path.parts), 'CACHE_PATH_REFUSED')
    need(path.name not in PRIVATE_NAMES, 'PRIVATE_OR_TRANSPORT_FILE_REFUSED')
    need(path.suffix in EXTENSIONS or path.name == 'SHA256SUMS', 'FILE_TYPE_REFUSED')
    need(not (path.suffix == '.json' and 'transfer' in path.name.lower()), 'TRANSFER_BUNDLE_REFUSED')
    return path


def read_source(relative):
    parts = relative_path(relative).parts
    path = SOURCE_ROOT
    for part in parts:
        path = path / part
        info = path.lstat()
        need(not stat.S_ISLNK(info.st_mode), 'SOURCE_SYMLINK_REFUSED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE_BYTES, 'BOUNDED_REGULAR_SOURCE_REQUIRED')
        chunks = []
        count = 0
        while True:
            data = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - count))
            if not data:
                break
            chunks.append(data)
            count += len(data)
            need(count <= MAX_FILE_BYTES, 'SOURCE_TOO_LARGE')
        after = os.fstat(fd)
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'SOURCE_CHANGED_DURING_READ')
        data = b''.join(chunks)
        need(len(data) == before.st_size, 'SOURCE_SIZE_CHANGED')
        return data
    finally:
        os.close(fd)


def check_json(relative, data):
    if not relative.endswith(('.json', '.jwk')):
        return
    value = json.loads(data.decode('utf-8-sig'))

    def walk(item):
        if isinstance(item, dict):
            for key, value in item.items():
                need(str(key).lower() not in SENSITIVE_JSON_KEYS, 'SENSITIVE_JSON_FIELD_REFUSED')
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(value)
    if relative.endswith('.jwk'):
        need(isinstance(value, dict) and value.get('kty') == 'RSA', 'PUBLIC_RSA_JWK_REQUIRED')
        need(not any(name in value for name in ('d', 'p', 'q', 'dp', 'dq', 'qi', 'oth', 'k')),
             'PRIVATE_JWK_MATERIAL_REFUSED')


def write_new(path, data):
    path = Path(path)
    need(path.is_absolute(), 'ABSOLUTE_OUTPUT_REQUIRED')
    need(path.parent.is_dir() and not path.parent.is_symlink(), 'EXISTING_OUTPUT_PARENT_REQUIRED')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allowlist-sha256', required=True)
    parser.add_argument('--output')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    need(bool(HASH.fullmatch(args.allowlist_sha256)), 'ALLOWLIST_SHA256_REQUIRED')
    need(args.verify_only or args.output, 'OUTPUT_OR_VERIFY_ONLY_REQUIRED')
    raw = read_source(ALLOWLIST_NAME)
    need(hashlib.sha256(raw).hexdigest() == args.allowlist_sha256, 'ALLOWLIST_HASH_CHANGED')
    manifest = json.loads(raw)
    need(manifest.get('schema') == 'hara.commander.closeout-allowlist.v1', 'ALLOWLIST_SCHEMA_REQUIRED')
    rows = manifest.get('files')
    need(isinstance(rows, list) and 0 < len(rows) <= MAX_ENTRIES, 'BOUNDED_ALLOWLIST_REQUIRED')
    envelope = {}
    receipt = {}
    total = 0
    for row in rows:
        need(isinstance(row, dict) and set(row) == {'source', 'destination', 'sha256', 'bytes'},
             'EXPLICIT_FILE_RECORD_REQUIRED')
        source = row['source']
        destination = str(relative_path(row['destination']))
        need(any(destination.startswith(prefix) for prefix in PREFIXES), 'REPOSITORY_DESTINATION_REFUSED')
        need(destination != ALLOWLIST_DESTINATION and destination not in envelope, 'DUPLICATE_DESTINATION_REFUSED')
        need(isinstance(row['sha256'], str) and bool(HASH.fullmatch(row['sha256'])), 'SOURCE_HASH_REQUIRED')
        data = read_source(source)
        digest = hashlib.sha256(data).hexdigest()
        need(type(row['bytes']) is int and len(data) == row['bytes'] and digest == row['sha256'],
             'SOURCE_PIN_CHANGED')
        check_json(source, data)
        total += len(data)
        need(total <= MAX_TOTAL_BYTES, 'BUNDLE_INPUT_TOO_LARGE')
        envelope[destination] = {'bytes': len(data), 'sha256': digest,
                                 'data_zlib': base64.b64encode(zlib.compress(data, 9)).decode('ascii')}
        receipt[destination] = {'source': source, 'bytes': len(data), 'sha256': digest}
    # Include the caller-pinned allowlist without an impossible self-hash entry.
    envelope[ALLOWLIST_DESTINATION] = {
        'bytes': len(raw), 'sha256': args.allowlist_sha256,
        'data_zlib': base64.b64encode(zlib.compress(raw, 9)).decode('ascii'),
    }
    receipt[ALLOWLIST_DESTINATION] = {
        'source': ALLOWLIST_NAME, 'bytes': len(raw), 'sha256': args.allowlist_sha256,
    }
    encoded = (json.dumps(envelope, sort_keys=True, separators=(',', ':')) + '\n').encode()
    summary = {'state': 'PINNED_INPUTS_VERIFIED' if args.verify_only else 'LOCAL_GIT_BUNDLE_PREPARED',
               'files': len(envelope), 'source_bytes': total + len(raw),
               'bundle_bytes': len(encoded), 'bundle_sha256': hashlib.sha256(encoded).hexdigest(),
               'allowlist_sha256': args.allowlist_sha256,
               'remote_mutation': False, 'repository_mutation': False}
    if not args.verify_only:
        output = Path(args.output)
        metadata = output.with_name(output.stem + '-manifest.json')
        need(not os.path.lexists(output) and not os.path.lexists(metadata), 'OUTPUT_ALREADY_EXISTS')
        write_new(output, encoded)
        write_new(metadata, (json.dumps({'summary': summary, 'files': receipt}, indent=2,
                                       sort_keys=True) + '\n').encode())
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = str(error)
        code = message if re.fullmatch('[A-Z][A-Z0-9_]{1,100}', message) else type(error).__name__
        print(json.dumps({'state': 'HOLD', 'error_code': code}), file=sys.stderr)
        raise SystemExit(2)
