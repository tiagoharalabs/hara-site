#!/usr/bin/env python3
"""Stage current UI with an exact signed commercial release; no cloud operations.

Bare public/ includes development sources and is not a release. Pass a
qualified signed --output directory to Wrangler --assets. The current source
has a Linux terminal-drain fix absent from the historical signed bundles, so
the default release stays on HOLD until a new official signature exists.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from verify_signed_distribution import verify_bundle

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'apps/commander'
PUBLIC = APP / 'public'
CURRENT_RELEASE = 'commercial-0.3.43-v5-terminal-drain'
ROLLBACK_RELEASE = 'commercial-0.3.43-v4-autoreconnect'
HISTORICAL_RELEASE = 'commercial-0.3.43-v3'
BUNDLES = {
    name: APP / 'release-bundles' / name
    for name in (CURRENT_RELEASE, ROLLBACK_RELEASE, HISTORICAL_RELEASE)
}
RELEASE_FILES = (
    'agent/linux.py', 'agent/windows.ps1',
    'install/linux.sh', 'install/windows.ps1',
    'release/agent-manifest.json', 'release/agent-manifest.sig.json',
    'release/release-signing-public.jwk', 'release/SHA256SUMS',
)
LINUX_RELEASE_REGRESSIONS = (
    'validate_process_terminal_drain.py', 'validate_process_continuous_drain.py',
    'validate_process_oneshot_pagination.py', 'validate_process_session_policy.py',
    'validate_result_delivery_outbox.py', 'validate_result_envelope_budget.py',
    'validate_file_cas_atomicity.py', 'validate_relay_burst_dispatch.py',
    'validate_mount_aware_resources.py',
)


def verified_file(root: Path, relative: str) -> Path:
    source = root / relative
    if source.is_symlink() or not source.is_file() or source.resolve() != source.absolute():
        raise RuntimeError('SIGNED_STAGE_UNSAFE_SOURCE:' + relative)
    source.relative_to(root)
    return source


def public_source_tree() -> str:
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:apps/commander/public'], cwd=ROOT, text=True,
    ).strip()


def committed_public_paths(source_tree: str) -> set[str]:
    listing = subprocess.check_output(
        ['git', 'ls-tree', '-r', '-z', '--name-only', source_tree], cwd=ROOT,
    ).decode().split('\0')
    return set(filter(None, listing))


def require_committed_public_source(relative: str, source: Path,
                                    source_tree: str) -> None:
    try:
        committed = subprocess.check_output(
            ['git', 'show', source_tree + ':' + relative],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('SIGNED_STAGE_UI_SOURCE_UNCOMMITTED:' + relative) from exc
    if source.read_bytes() != committed:
        raise RuntimeError('SIGNED_STAGE_UI_SOURCE_UNCOMMITTED:' + relative)


def stage_tree_sha256(output: Path, paths: set[str]) -> str:
    entries = []
    for relative in sorted(paths):
        data = verified_file(output, relative).read_bytes()
        entries.append((relative, len(data), hashlib.sha256(data).hexdigest()))
    encoded = json.dumps(entries, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_bundle(bundle: Path) -> dict:
    if bundle not in BUNDLES.values():
        raise RuntimeError('SIGNED_STAGE_BUNDLE_NOT_APPROVED')
    if not bundle.is_dir():
        raise RuntimeError('SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE')
    return verify_bundle(bundle)


def require_current_linux_regressions(bundle: Path) -> None:
    if bundle.name != CURRENT_RELEASE:
        return
    for script in LINUX_RELEASE_REGRESSIONS:
        proc = subprocess.run(
            ['python3', '-B', str(APP / 'scripts' / script),
             '--source', str(bundle / 'agent/linux.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        if proc.returncode:
            raise RuntimeError('SIGNED_STAGE_LINUX_PROCESS_DRAIN_FAILED:' + script)


def _inspect_stage(output: Path, bundle: Path, release_metadata: dict,
                   expected_tree_sha256: str | None = None) -> dict:
    if (not output.is_absolute() or output.is_symlink() or not output.is_dir()
            or output.resolve() != output.absolute()):
        raise RuntimeError('SIGNED_STAGE_UNSAFE_SOURCE:root')
    source_tree = public_source_tree()
    expected_paths = committed_public_paths(source_tree)
    staged_paths = {
        path.relative_to(output).as_posix()
        for path in output.rglob('*') if path.is_file() or path.is_symlink()
    }
    if staged_paths != expected_paths:
        raise RuntimeError('SIGNED_STAGE_FILESET_DRIFT')
    for relative in sorted(expected_paths):
        staged = verified_file(output, relative)
        source = verified_file(bundle if relative in RELEASE_FILES else PUBLIC, relative)
        if relative not in RELEASE_FILES:
            require_committed_public_source(relative, source, source_tree)
        if staged.read_bytes() != source.read_bytes():
            code = ('SIGNED_STAGE_RELEASE_DRIFT:' if relative in RELEASE_FILES
                    else 'SIGNED_STAGE_UI_CHANGED:')
            raise RuntimeError(code + relative)
    if verify_bundle(output) != release_metadata:
        raise RuntimeError('SIGNED_STAGE_RELEASE_VERIFICATION_CHANGED')
    digest = stage_tree_sha256(output, expected_paths)
    if expected_tree_sha256 is not None and digest != expected_tree_sha256:
        raise RuntimeError('SIGNED_STAGE_TREE_DIGEST_MISMATCH')
    return {**release_metadata, 'stage_tree_sha256': digest,
            'source_public_tree': source_tree}


def require_signed_stage(output: Path, *, expected_bundle: Path | None = None,
                         expected_tree_sha256: str | None = None) -> dict:
    """Bind promotion/readback to the exact approved, signed asset set."""
    bundle = expected_bundle or BUNDLES[CURRENT_RELEASE]
    release_metadata = validate_bundle(bundle)
    require_current_linux_regressions(bundle)
    return _inspect_stage(output, bundle, release_metadata, expected_tree_sha256)


def stage(output: Path, bundle: Path = BUNDLES[CURRENT_RELEASE], *, rollback_only: bool = False) -> dict:
    release_metadata = validate_bundle(bundle)
    if bundle.name != CURRENT_RELEASE and not rollback_only:
        raise RuntimeError('SIGNED_STAGE_HISTORICAL_RELEASE_REQUIRES_ROLLBACK_ONLY')
    require_current_linux_regressions(bundle)
    config = json.loads((APP / 'wrangler.jsonc').read_text())
    if config['assets']['directory'] != 'signed-assets-stage-required':
        raise RuntimeError('SIGNED_STAGE_RAW_PUBLIC_CONFIG_DENIED')
    if output.exists() or output.is_symlink():
        raise RuntimeError('SIGNED_STAGE_DESTINATION_MUST_NOT_EXIST')
    if output.parent.resolve() != output.parent.absolute():
        raise RuntimeError('SIGNED_STAGE_DESTINATION_PARENT_SYMLINK')
    source_tree = public_source_tree()
    listing = committed_public_paths(source_tree)
    originals = []
    for relative in sorted(listing):
        if '..' in Path(relative).parts or Path(relative).is_absolute():
            raise RuntimeError('SIGNED_STAGE_RELATIVE_PATH_INVALID')
        source = verified_file(PUBLIC, relative)
        if relative not in RELEASE_FILES:
            require_committed_public_source(relative, source, source_tree)
        originals.append((relative, source))
    # Check every release source before writing anything.
    release = [(name, verified_file(bundle, name)) for name in RELEASE_FILES]
    output.mkdir(mode=0o700)
    for relative, source in originals:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    overrides = []
    for relative, source in release:
        target = output / relative
        if target.exists() and target.read_bytes() != source.read_bytes():
            overrides.append(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    hashes = {}
    for relative, source in release:
        blob = (output / relative).read_bytes()
        if blob != source.read_bytes():
            raise RuntimeError('SIGNED_STAGE_RELEASE_READBACK_FAILED:' + relative)
        hashes[relative] = hashlib.sha256(blob).hexdigest()
    stage_metadata = _inspect_stage(output, bundle, release_metadata)
    return {
        'schema': 'hara.commander-signed-asset-stage.v1',
        'state': 'ROLLBACK_ONLY_KNOWN_PROCESS_DRAIN_REGRESSION' if rollback_only else 'PASS',
        'release': bundle.name,
        'agent_version': release_metadata['agent_version'],
        'cryptographic_signature': release_metadata['signature'],
        'tracked_public_files': len(originals), 'signed_files_verified': len(release),
        'candidate_sources_replaced_only_in_stage': overrides,
        'ui_unchanged': True, 'signed_sha256': hashes,
        'stage_tree_sha256': stage_metadata['stage_tree_sha256'],
        'source_public_tree': stage_metadata['source_public_tree'],
        'cloud_operations': False, 'private_keys_read': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true')
    action.add_argument('--output', type=Path)
    action.add_argument('--verify-assets', type=Path,
                        help='recheck the exact staged upload directory')
    parser.add_argument('--expected-tree-sha256',
                        help='digest recorded when the upload directory was staged')
    parser.add_argument('--bundle', choices=tuple(BUNDLES), default=CURRENT_RELEASE)
    parser.add_argument('--rollback-only', action='store_true')
    args = parser.parse_args()
    if args.rollback_only and args.bundle == CURRENT_RELEASE:
        raise SystemExit('SIGNED_STAGE_ROLLBACK_FLAG_REQUIRES_HISTORICAL_BUNDLE')
    if args.bundle != CURRENT_RELEASE and not args.rollback_only:
        raise SystemExit('SIGNED_STAGE_HISTORICAL_RELEASE_REQUIRES_ROLLBACK_ONLY')
    if args.verify_assets:
        if not args.expected_tree_sha256 or not re.fullmatch(r'[0-9a-f]{64}', args.expected_tree_sha256):
            raise SystemExit('SIGNED_STAGE_EXPECTED_TREE_SHA256_REQUIRED')
        report = require_signed_stage(
            args.verify_assets, expected_bundle=BUNDLES[args.bundle],
            expected_tree_sha256=args.expected_tree_sha256,
        )
        print(json.dumps({
            'state': 'ROLLBACK_ONLY_KNOWN_PROCESS_DRAIN_REGRESSION' if args.rollback_only else 'PASS',
            'release': args.bundle,
            'stage_tree_sha256': report['stage_tree_sha256'],
            'source_public_tree': report['source_public_tree'],
            'signed_manifest_sha256': report['manifest_sha256'],
            'verified_files': len(committed_public_paths(report['source_public_tree'])),
            'cloud_operations': False,
        }, indent=2, sort_keys=True))
        return 0
    if args.expected_tree_sha256:
        raise SystemExit('SIGNED_STAGE_EXPECTED_TREE_SHA256_REQUIRES_VERIFY_ASSETS')
    if args.output:
        output = args.output
        if not output.is_absolute() or not any(parent in output.parents for parent in (Path('/tmp'), Path('/tmp_hara'))):
            raise SystemExit('SIGNED_STAGE_OUTPUT_REQUIRES_PRIVATE_TMP_ABSOLUTE_PATH')
        if not output.parent.is_dir():
            raise SystemExit('SIGNED_STAGE_OUTPUT_PARENT_MUST_EXIST')
        report = stage(output, BUNDLES[args.bundle], rollback_only=args.rollback_only)
        report['stage_path'] = str(output)
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        with tempfile.TemporaryDirectory(prefix='hara-signed-assets-check-') as temporary:
            report = stage(Path(temporary) / 'assets', BUNDLES[args.bundle], rollback_only=args.rollback_only)
            assert report['signed_files_verified'] == 8
            assert report['ui_unchanged']
        print('COMMANDER_SIGNED_ASSET_STAGE=' + report['state'])
        print('COMMANDER_SIGNED_ASSET_STAGE_RELEASE=' + args.bundle.upper().replace('-', '_').replace('.', '_'))
        print('COMMANDER_SIGNED_ASSET_STAGE_UI_UNCHANGED=PASS')
        print('COMMANDER_SIGNED_ASSET_STAGE_CLOUD_OPERATIONS=FALSE')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
