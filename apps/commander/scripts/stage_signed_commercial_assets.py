#!/usr/bin/env python3
"""Stage current UI + exact verified commercial release; no cloud operations.

Bare public/ includes development installer sources and is NOT a release
artifact. Use --output /tmp_hara/<new-directory> and pass that exact directory
to Wrangler --assets. Default/--check validates a disposable local stage.
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

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'apps/commander'
PUBLIC = APP / 'public'
SIGNED = APP / 'release-bundles/commercial-0.3.43-v3'
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


def validate_bundle() -> None:
    proc = subprocess.run(
        [sys.executable, '-B', str(APP / 'scripts/validate_signed_commercial_v3_bundle.py')],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    if proc.returncode:
        raise RuntimeError('SIGNED_STAGE_BUNDLE_SIGNATURE_OR_HASH_INVALID')


def stage(output: Path) -> dict:
    validate_bundle()
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
    release = [(name, verified_file(SIGNED, name)) for name in RELEASE_FILES]
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
    for name in ('index.html', 'app.js', 'styles.css'):
        if (output / name).read_bytes() != (PUBLIC / name).read_bytes():
            raise RuntimeError('SIGNED_STAGE_UI_CHANGED:' + name)
    return {
        'schema': 'hara.commander-signed-asset-stage.v1', 'state': 'PASS',
        'release': 'commercial-0.3.43-v3',
        'tracked_public_files': len(originals), 'signed_files_verified': len(release),
        'candidate_sources_replaced_only_in_stage': overrides,
        'ui_unchanged': True, 'signed_sha256': hashes,
        'cloud_operations': False, 'private_keys_read': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.check and args.output:
        raise SystemExit('SIGNED_STAGE_CHECK_AND_OUTPUT_MUTUALLY_EXCLUSIVE')
    if args.output:
        output = args.output
        if not output.is_absolute() or not str(output).startswith('/tmp_hara/'):
            raise SystemExit('SIGNED_STAGE_OUTPUT_REQUIRES_TMP_HARA_ABSOLUTE_PATH')
        if not output.parent.is_dir():
            raise SystemExit('SIGNED_STAGE_OUTPUT_PARENT_MUST_EXIST')
        report = stage(output)
        report['stage_path'] = str(output)
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        with tempfile.TemporaryDirectory(prefix='hara-signed-assets-check-') as temporary:
            report = stage(Path(temporary) / 'assets')
            assert report['signed_files_verified'] == 8
            assert report['ui_unchanged']
        print('COMMANDER_SIGNED_ASSET_STAGE=PASS')
        print('COMMANDER_SIGNED_ASSET_STAGE_RELEASE=COMMERCIAL_0_3_43_V3')
        print('COMMANDER_SIGNED_ASSET_STAGE_UI_UNCHANGED=PASS')
        print('COMMANDER_SIGNED_ASSET_STAGE_CLOUD_OPERATIONS=FALSE')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
