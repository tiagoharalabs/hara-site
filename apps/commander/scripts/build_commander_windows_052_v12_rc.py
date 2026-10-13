#!/usr/bin/env python3
"""Prepare a privately signed Windows 0.3.52-v12 RC from final reviewed source.

Preserve historical signed bundles and Linux bytes. Reuse the custodied v2
signer; public/customer distribution and installed Agents are never modified.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import build_commander_commercial_signed_v2 as signer

APP = signer.APP
VERSION = "0.3.52"
APPROVED_SOURCE_SHA256 = "817325667ea552136efa10d807148fa4dc6d035aca24046c884f444a4fb61ebc"
signer.VERSION = VERSION
BASE = APP / "release-bundles/commercial-0.3.51-v11-rc"
NEW = APP / "release-bundles/commercial-0.3.52-v12-rc"
FILESET = signer.FILESET
EXTRA = ("release/agent-manifest.json", "release/agent-manifest.sig.json",
         "release/release-signing-public.jwk", "release/SHA256SUMS")
OLD_ANCHOR = b'agent_version="0.3.51"'
NEW_ANCHOR = b'agent_version="0.3.52"'
CANONICAL_NODE = Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules")
FEATURES = (
    b"Invoke-WithLocalApprovalLock", b"Test-LocalApprovalRequestCurrent",
    b"Initialize-LocalApprovalConsoleInput", b"Read-LocalApprovalConsoleKey",
    b"Clear-LocalApprovalConsoleInput", b"Read-LocalApprovalResponse",
    b"Publish-LocalApprovalResponse", b"Remove-LocalApprovalFiles",
    b"Respond-ToLocalApprovalRequest", b"HaraWindowsProcessSession",
    b"FILE_PRECONDITION_FAILED", b"PROCESS_SESSION_CAPACITY",
    b"Test-LocalApprovalConsumerAlive", b"consumer_pid", b"consumer_started_at_utc",
    b"function Get-OperatorSession", b"public bool Stop(bool force)",
    b"mutation_performed=$mutationPerformed",
)

def fail(code):
    raise RuntimeError("COMMANDER_WINDOWS_052_V12_" + code)

def historical_verification():
    # The latest immutable validator checks v3 and every Windows44..50 ancestor.
    # Re-running every recursive ancestor here duplicates the same verification.
    for name in ("validate_signed_windows_051_v11_rc.py",):
        proc = subprocess.run([sys.executable, "-B", str(APP / "scripts" / name)],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            fail("PREVIOUS_SIGNED_RELEASE_INVALID:" + name)
    if not BASE.is_dir() or BASE.is_symlink():
        fail("PREVIOUS_RELEASE_INVALID")
    pub, _ = signer.public_key()
    if json.loads((BASE / "release/release-signing-public.jwk").read_bytes()) != pub:
        fail("PREVIOUS_KEY_AUTHORITY_DRIFT")

def expected_installer():
    source = (BASE / "install/windows.ps1").read_bytes()
    if source.count(OLD_ANCHOR) != 3:
        fail("INSTALLER_VERSION_ANCHOR_INVALID")
    return source.replace(OLD_ANCHOR, NEW_ANCHOR)

def pin_canonical_installer():
    path = APP / "public/install/windows.ps1"
    if not path.is_file() or path.is_symlink():
        fail("CANONICAL_INSTALLER_INVALID")
    raw = path.read_bytes()
    pub, _ = signer.public_key()
    for label, key in (("Kid", "kid"), ("N", "n"), ("E", "e")):
        pattern = rb'\$ReleaseSigning' + label.encode() + rb' = "[^"]+"'
        raw, count = re.subn(pattern, lambda _: b'$ReleaseSigning' + label.encode() +
                            b' = "' + pub[key].encode() + b'"', raw)
        if count != 1:
            fail("CANONICAL_SIGNER_PIN_MISSING")
    return raw

def expected_agent():
    path = APP / "public/agent/windows.ps1"
    if not path.is_file() or path.is_symlink():
        fail("CANONICAL_AGENT_INVALID")
    source = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", APPROVED_SOURCE_SHA256):
        fail("FINAL_SOURCE_REVIEW_PIN_MISSING")
    if signer.sha(source) != APPROVED_SOURCE_SHA256:
        fail("APPROVED_SOURCE_HASH_DRIFT")
    if source.count(b'$AgentVersion = "0.3.52"') != 1:
        fail("AGENT_VERSION_INVALID")
    if b"WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED" in source:
        fail("UNSUPPORTED_APPROVAL_CODE_REMAINS")
    if b"action_summary=$null" not in source:
        fail("METADATA_ONLY_CONSOLE_LOG_MISSING")
    if b"SELF_TEST_LOCAL_CONSOLE_PRIVATE_COMMAND_PERSISTED" not in source:
        fail("PRIVACY_SELFTEST_MISSING")
    if b"$ApprovalTimeoutSeconds = 900" not in source:
        fail("APPROVAL_WINDOW_NOT_PINNED")
    match = re.search(rb"(?ms)^function Respond-ToLocalApprovalRequest\b.*?(?=^function |^\$script:ManagedWindowsSessions)", source)
    if not match or b"Read-Host" in match.group(0):
        fail("BLOCKING_APPROVAL_CONSOLE_INPUT_REMAINS")
    for feature in FEATURES:
        if feature not in source:
            fail("REQUIRED_FEATURE_MISSING:" + feature.decode())
    if b'$bytes=[Text.Encoding]::UTF8.GetBytes($json)' not in source or b'-ContentType "application/json; charset=utf-8"' not in source or b'-Body $bytes' not in source:
        fail("UTF8_TRANSPORT_NOT_PINNED")
    return source

def final_source_verification():
    agent = expected_agent()
    installer = expected_installer()
    if pin_canonical_installer() != (APP / "release-bundles/commercial-0.3.49-v9-rc/install/windows.ps1").read_bytes():
        fail("CANONICAL_049_INSTALLER_NOT_PRESERVED")
    return agent, installer

def validate_stage_source(stage):
    agent, installer = final_source_verification()
    public = stage / "apps/commander/public"
    for rel in FILESET:
        expected = agent if rel == "agent/windows.ps1" else installer if rel == "install/windows.ps1" else (BASE / rel).read_bytes()
        path = public / rel
        if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
            fail("STAGING_SOURCE_DRIFT:" + rel)
    previous = json.loads((BASE / "release/agent-manifest.json").read_bytes())
    expected = {**previous, "agent_version": VERSION,
                "files": [{"bytes": len((public / rel).read_bytes()), "path": rel,
                           "sha256": signer.sha((public / rel).read_bytes())}
                          for rel in FILESET]}
    if (public / "release/agent-manifest.json").read_bytes() != signer.json_bytes(expected):
        fail("STAGING_MANIFEST_DRIFT")
    if (public / "release/release-signing-public.jwk").read_bytes() != (BASE / "release/release-signing-public.jwk").read_bytes():
        fail("STAGING_KEY_DRIFT")
    checksums = "".join(f"{row['sha256']}  {row['path']}\n" for row in expected["files"])
    if (public / "release/SHA256SUMS").read_text(encoding="utf-8") != checksums:
        fail("STAGING_CHECKSUM_DRIFT")

def prepare(stage):
    historical_verification()
    if stage.exists() or NEW.exists():
        fail("IMMUTABLE_RELEASE_TARGET_EXISTS")
    agent, installer = final_source_verification()
    node = signer.ROOT / "node_modules"
    if not node.is_dir():
        node = CANONICAL_NODE
    if not node.is_dir():
        fail("NPM_DEPENDENCIES_MISSING")
    stage.mkdir(mode=0o700, parents=True)
    target = stage / "apps/commander"
    for folder in ("src", "migrations", "public"):
        shutil.copytree(APP / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copy2(APP / "wrangler.jsonc", target / "wrangler.jsonc")
    (stage / "node_modules").symlink_to(node, target_is_directory=True)
    public = target / "public"
    for rel in FILESET:
        data = agent if rel == "agent/windows.ps1" else installer if rel == "install/windows.ps1" else (BASE / rel).read_bytes()
        (public / rel).write_bytes(data)
    (public / "release/release-signing-public.jwk").write_bytes((BASE / "release/release-signing-public.jwk").read_bytes())
    previous = json.loads((BASE / "release/agent-manifest.json").read_bytes())
    manifest = {**previous, "agent_version": VERSION,
                "files": [{"bytes": len((public / rel).read_bytes()), "path": rel,
                           "sha256": signer.sha((public / rel).read_bytes())} for rel in FILESET]}
    (public / "release/agent-manifest.json").write_bytes(signer.json_bytes(manifest))
    (public / "release/SHA256SUMS").write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in manifest["files"]), encoding="utf-8")
    stale = public / "release/agent-manifest.sig.json"
    if stale.exists():
        stale.unlink()
    validate_stage_source(stage)
    print("WINDOWS_0_3_52_V12_RC_STAGE_PREPARED")

def sign(stage):
    historical_verification()
    validate_stage_source(stage)
    if NEW.exists():
        fail("RELEASE_ALREADY_EXISTS")
    signer.sign(stage)
    validate_stage_source(stage)
    print("WINDOWS_0_3_52_V12_RC_SIGNED")

def freeze(stage):
    historical_verification()
    validate_stage_source(stage)
    signer.verify(stage)
    if NEW.exists():
        fail("RELEASE_ALREADY_EXISTS")
    destination = Path(tempfile.mkdtemp(prefix=".commercial-0.3.52-v12-freeze-", dir=NEW.parent))
    try:
        public = stage / "apps/commander/public"
        for rel in (*FILESET, *EXTRA):
            source = public / rel
            if not source.is_file() or source.is_symlink():
                fail("STAGING_FILE_INVALID:" + rel)
            dest = destination / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            if source.read_bytes() != dest.read_bytes():
                fail("FROZEN_FILE_HASH_MISMATCH")
        (destination / "README.md").write_text(
            "# Windows 0.3.52-v12 RC — Founder lab candidate\n\n"
            "RS256 signed private release with explicit UTF-8 JSON transport and a 15-minute local approval window,\n"
            "deadline, request/session binding and consumer PID/start liveness.\n"
            "Historical v3/v4/v5/v6/v7/v8/v9 releases and signed Linux assets are preserved.\n"
            "This bundle does not deploy to production or modify installed Agents.\n"
            "Positive local human approval and live MCP tests remain required.\n",
            encoding="utf-8")
        validate_stage_source(stage)
        destination.rename(NEW)
    finally:
        if destination.exists():
            shutil.rmtree(destination)
    print("WINDOWS_0_3_52_V12_RC_SIGNED_AND_FROZEN")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "sign", "freeze"))
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    stage = signer.protect(args.stage)
    {"prepare": prepare, "sign": sign, "freeze": freeze}[args.action](stage)

if __name__ == "__main__":
    main()
