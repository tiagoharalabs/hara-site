#!/usr/bin/env python3
"""Build a private, immutable SOURCE review. No installer or release authority."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

CANDIDATE = 'apps/commander/release-candidates/commercial-0.3.56-source'
AGENTS = tuple(CANDIDATE + '/agent/' + name for name in (
    'linux.py', 'windows.ps1', 'event_v2_dev.py', 'event_v2_dev.ps1',
    'event_v2_wire.py', 'event_v2_wire.ps1'))
HARNESSES = tuple('apps/commander/scripts/' + name for name in (
    'test_event_v2_commercial_windows_0356_r163.ps1',
    'test_event_v2_commercial_windows_heartbeat_r163.ps1',
    'test_commercial_056_windows_recovery.ps1',
    'test_commercial_056_windows_supervisor.ps1',
    'test_commercial_056_windows_job_native.ps1'))
PROVENANCE = (CANDIDATE + '/draft-source-policy.json', CANDIDATE + '/origin.json')
ALIASES = {
    'valk/windows-agent-0.3.56-eventv2-review.txt': AGENTS[1],
    'valk/event-v2-dev-0.3.56-review.txt': AGENTS[3],
    'valk/event-v2-wire-0.3.56-review.txt': AGENTS[5],
}


def _git(repo, *args):
    env = dict(os.environ, GIT_PAGER='cat', PAGER='cat', GIT_TERMINAL_PROMPT='0')
    # Do not inherit an alternate index/worktree from the caller.
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(name, None)
    result = subprocess.run(['git', '-C', str(repo), *args], env=env,
                            capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError('SOURCE_REVIEW_GIT_READ_FAILED')
    return result.stdout


def _resolved(repo, ref):
    if not isinstance(ref, str) or not ref or ref.startswith('-'):
        raise ValueError('SOURCE_REVIEW_REF_INVALID')
    head = _git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise ValueError('SOURCE_REVIEW_REF_INVALID')
    return head


def build_review(repo, output, ref='HEAD', expected_head=None):
    repo, output = Path(repo), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('SOURCE_REVIEW_OUTPUT_EXISTS')
    if not output.parent.is_dir() or output.parent.resolve() != output.parent:
        raise ValueError('SOURCE_REVIEW_PRIVATE_PARENT_REQUIRED')
    if output.parent.stat().st_mode & 0o077:
        raise ValueError('SOURCE_REVIEW_PRIVATE_PARENT_REQUIRED')
    head = _resolved(repo, ref)
    if expected_head is not None and head != expected_head:
        raise ValueError('SOURCE_REVIEW_HEAD_MISMATCH')
    tree = _git(repo, 'rev-parse', head + '^{tree}').decode().strip()
    files = {}
    for relative in AGENTS + HARNESSES + PROVENANCE:
        entry = _git(repo, 'ls-tree', head, '--', relative).decode().strip()
        if not entry:
            raise ValueError('SOURCE_REVIEW_MISSING_SOURCE:' + relative)
        mode, kind, _object = entry.split('\t', 1)[0].split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('SOURCE_REVIEW_REGULAR_BLOB_REQUIRED')
        raw = _git(repo, 'show', head + ':' + relative)
        if not raw or len(raw) > 2 * 1024 * 1024:
            raise ValueError('SOURCE_REVIEW_SOURCE_SIZE_INVALID')
        files['source/' + relative] = raw
    linux = ast.parse(files['source/' + AGENTS[0]].decode('utf-8-sig'))
    versions = [node.value.value for node in linux.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(target, ast.Name) and target.id == 'AGENT_VERSION'
                        for target in node.targets)]
    windows = files['source/' + AGENTS[1]].decode('utf-8-sig')
    if versions != ['0.3.56'] or not re.search(
            r'''(?m)^\$AgentVersion\s*=\s*(["'])0\.3\.56\1\s*$''', windows):
        raise ValueError('SOURCE_REVIEW_VERSION_MISMATCH')
    for alias, relative in ALIASES.items():
        files[alias] = files['source/' + relative]  # bytes, without decoding
    if _resolved(repo, ref) != head:
        raise ValueError('SOURCE_REVIEW_REF_CHANGED')
    index = {
        'schema': 'hara.commander.0356.source-review.v1',
        'source_commit': head, 'source_tree': tree, 'version': '0.3.56',
        'purpose': 'PRIVATE_SOURCE_REVIEW_NOT_INSTALLABLE_RELEASE',
        'native_acceptance': False, 'installable': False,
        'independent_pin': None, 'signature': None, 'admission_receipt': None,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
                  for name, raw in sorted(files.items())},
    }
    files['review-index.json'] = (json.dumps(index, sort_keys=True, indent=2) + '\n').encode()
    archive_bytes = io.BytesIO()
    with gzip.GzipFile(fileobj=archive_bytes, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name, raw in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                info.mode = 0o400
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ''
                archive.addfile(info, io.BytesIO(raw))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(output, flags, 0o600)
    except FileExistsError as error:
        raise FileExistsError('SOURCE_REVIEW_OUTPUT_EXISTS') from error
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(archive_bytes.getvalue())
            target.flush()
            os.fsync(target.fileno())
            os.fchmod(target.fileno(), 0o400)
    except BaseException:
        # Never delete a replacement another executor may have created while
        # this invocation was failing, even in the private output directory.
        try:
            current = output.lstat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                output.unlink()
        except FileNotFoundError:
            pass
        raise
    return {'source_commit': head, 'source_tree': tree, 'path': str(output),
            'sha256': hashlib.sha256(archive_bytes.getvalue()).hexdigest(),
            'installable': False, 'native_acceptance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    print(json.dumps(build_review(args.repo, args.output, args.ref, args.expected_head), sort_keys=True))


if __name__ == '__main__':
    main()
