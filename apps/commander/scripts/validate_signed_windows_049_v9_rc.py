#!/usr/bin/env python3
"""Verify immutable historical Windows 0.3.49-v9 signature and reviewed source pin."""
from __future__ import annotations
import json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import build_commander_windows_049_v9_rc as release

APP = release.APP
OLD = release.BASE
NEW = release.NEW
FILES = release.FILESET

def need(ok, code):
    if not ok:
        raise AssertionError("WINDOWS049_RC_" + code)

def main():
    release.historical_verification()
    need(NEW.is_dir() and not NEW.is_symlink(), "BUNDLE_INVALID")
    for rel in (*FILES, *release.EXTRA):
        path = NEW / rel
        need(path.is_file() and not path.is_symlink(), "FILE_MISSING_OR_SYMLINK:" + rel)
        parent = path.parent
        while parent != NEW:
            need(not parent.is_symlink(), "PARENT_SYMLINK:" + rel)
            parent = parent.parent
    raw = (NEW / "release/agent-manifest.json").read_bytes()
    manifest = json.loads(raw)
    previous = json.loads((OLD / "release/agent-manifest.json").read_bytes())
    sig = json.loads((NEW / "release/agent-manifest.sig.json").read_bytes())
    pub, key = release.signer.public_key()
    jwk = json.loads((NEW / "release/release-signing-public.jwk").read_bytes())
    need(jwk == pub, "PINNED_V2_KEY_AUTHORITY")
    need((NEW / "release/release-signing-public.jwk").read_bytes() ==
         (OLD / "release/release-signing-public.jwk").read_bytes(), "KEY_NOT_IDENTICAL")
    need(sig.get("schema") == "hara.commander-release-signature.v1" and
         sig.get("alg") == "RS256" and sig.get("kid") == release.signer.KID and
         sig.get("manifest_sha256") == release.signer.sha(raw), "SIGNATURE_ENVELOPE")
    key.verify(release.signer.unb64(sig["signature"]), raw,
               padding.PKCS1v15(), hashes.SHA256())
    rows = manifest.get("files")
    need(isinstance(rows, list) and len(rows) == len(FILES) and
         all(isinstance(row, dict) for row in rows) and
         {row.get("path") for row in rows} == set(FILES), "MANIFEST_FILES")
    for row in rows:
        blob = (NEW / row["path"]).read_bytes()
        need(type(row.get("bytes")) is int and len(blob) == row["bytes"] and
             release.signer.sha(blob) == row.get("sha256"), "FILE_DIGEST:" + row["path"])
    expected = {**previous, "agent_version": release.VERSION,
                "files": [{"bytes": len((NEW / rel).read_bytes()), "path": rel,
                           "sha256": release.signer.sha((NEW / rel).read_bytes())}
                          for rel in FILES]}
    need(raw == release.signer.json_bytes(expected), "EXACT_MANIFEST_SCOPE")
    need(manifest.get("schema") == "hara.commander-agent-release.v1" and
         manifest.get("agent_version") == "0.3.49" and
         manifest.get("channel") == "stable", "MANIFEST_VERSION")
    for rel in ("agent/linux.py", "install/linux.sh"):
        need((NEW / rel).read_bytes() == (OLD / rel).read_bytes(),
             "LINUX_COMPONENT_CHANGED:" + rel)
    agent = (NEW / "agent/windows.ps1").read_bytes()
    installer = release.expected_installer()
    need(release.signer.sha(agent) == release.APPROVED_SOURCE_SHA256,
         "IMMUTABLE_SIGNED_V49_AGENT_SHA")
    need(b'$AgentVersion = "0.3.49"' in agent and b'$ApprovalTimeoutSeconds = 900' in agent,
         "IMMUTABLE_V49_VERSION_AND_APPROVAL_WINDOW")
    need((NEW / "install/windows.ps1").read_bytes() == installer,
         "WINDOWS_INSTALLER_EXTRA_MUTATION")
    need((NEW / "release/SHA256SUMS").read_text(encoding="utf-8") ==
         "".join(f"{row['sha256']}  {row['path']}\n" for row in rows), "CHECKSUM_INDEX")
    print(json.dumps({
        "schema": "hara.commander-windows049-rc-signature-validation.v1",
        "state": "PASS", "agent_version": "0.3.49",
        "signature": "RS256_RSA3072", "authority": "commander-release-v2",
        "four_files_authenticated": True,
        "historical_windows_source_sha256_pinned": True,
        "linux_agent_byte_identical": True, "linux_installer_byte_identical": True,
        "old_v3_v4_v5_v6_v7_v8_preserved": True, "approval_deadline_revalidation_pinned": True,
        "approval_window_seconds": 900,
        "production_deployment": False, "customer_agent_modified": False
    }, sort_keys=True))

if __name__ == "__main__":
    main()
