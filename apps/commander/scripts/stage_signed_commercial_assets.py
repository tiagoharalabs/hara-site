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


def verified_file(root: Path, relative: str) -> Path:
    source = root / relative
    if source.is_symlink() or not source.is_file() or source.resolve() != source.absolute():
        raise RuntimeError('SIGNED_STAGE_UNSAFE_SOURCE:' + relative)
    source.relative_to(root)
    return source


def validate_bundle(bundle: Path) -> dict:
    if bundle not in BUNDLES.values():
        raise RuntimeError('SIGNED_STAGE_BUNDLE_NOT_APPROVED')
    if not bundle.is_dir():
        raise RuntimeError('SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE')
    return verify_bundle(bundle)


def stage(output: Path, bundle: Path = BUNDLES[CURRENT_RELEASE], *, rollback_only: bool = False) -> dict:
    release_metadata = validate_bundle(bundle)
    if bundle.name != CURRENT_RELEASE and not rollback_only:
        raise RuntimeError('SIGNED_STAGE_HISTORICAL_RELEASE_REQUIRES_ROLLBACK_ONLY')
    if bundle.name == CURRENT_RELEASE:
        for script in ('validate_process_terminal_drain.py', 'validate_process_continuous_drain.py',
                       'validate_process_oneshot_pagination.py',
                       'validate_result_delivery_outbox.py', 'validate_result_envelope_budget.py'):
            proc = subprocess.run(
                ['python3', '-B', str(APP / 'scripts' / script),
                 '--source', str(bundle / 'agent/linux.py')],
                cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
            )
            if proc.returncode:
                raise RuntimeError('SIGNED_STAGE_LINUX_PROCESS_DRAIN_FAILED:' + script)
    config = json.loads((APP / 'wrangler.jsonc').read_text())
    if config['assets']['directory'] != 'signed-assets-stage-required':
        raise RuntimeError('SIGNED_STAGE_RAW_PUBLIC_CONFIG_DENIED')
    if output.exists() or output.is_symlink():
        raise RuntimeError('SIGNED_STAGE_DESTINATION_MUST_NOT_EXIST')
    if output.parent.resolve() != output.parent.absolute():
        raise RuntimeError('SIGNED_STAGE_DESTINATION_PARENT_SYMLINK')
    prefix = 'apps/commander/public/'
    listing = subprocess.check_output(
        ['git', 'ls-files', '-z', '--', prefix], cwd=ROOT,
    ).decode().split('\0')
    originals = []
    for name in filter(None, listing):
        if not name.startswith(prefix):
            raise RuntimeError('SIGNED_STAGE_TRACKED_PATH_INVALID')
        relative = name[len(prefix):]
        if '..' in Path(relative).parts or Path(relative).is_absolute():
            raise RuntimeError('SIGNED_STAGE_RELATIVE_PATH_INVALID')
        originals.append((relative, verified_file(PUBLIC, relative)))
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
    if verify_bundle(output) != release_metadata:
        raise RuntimeError('SIGNED_STAGE_RELEASE_VERIFICATION_CHANGED')
    for name in ('index.html', 'app.js', 'styles.css'):
        if (output / name).read_bytes() != (PUBLIC / name).read_bytes():
            raise RuntimeError('SIGNED_STAGE_UI_CHANGED:' + name)
    return {
        'schema': 'hara.commander-signed-asset-stage.v1',
        'state': 'ROLLBACK_ONLY_KNOWN_PROCESS_DRAIN_REGRESSION' if rollback_only else 'PASS',
        'release': bundle.name,
        'agent_version': release_metadata['agent_version'],
        'cryptographic_signature': release_metadata['signature'],
        'tracked_public_files': len(originals), 'signed_files_verified': len(release),
        'candidate_sources_replaced_only_in_stage': overrides,
        'ui_unchanged': True, 'signed_sha256': hashes,
        'cloud_operations': False, 'private_keys_read': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--bundle', choices=tuple(BUNDLES), default=CURRENT_RELEASE)
    parser.add_argument('--rollback-only', action='store_true')
    args = parser.parse_args()
    if args.check and args.output:
        raise SystemExit('SIGNED_STAGE_CHECK_AND_OUTPUT_MUTUALLY_EXCLUSIVE')
    if args.rollback_only and args.bundle == CURRENT_RELEASE:
        raise SystemExit('SIGNED_STAGE_ROLLBACK_FLAG_REQUIRES_HISTORICAL_BUNDLE')
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
