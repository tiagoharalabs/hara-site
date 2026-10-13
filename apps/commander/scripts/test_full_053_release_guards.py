#!/usr/bin/env python3
"""Thirteen unsigned tamper controls for the independently authenticated .53 RC."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import validate_signed_full_053_v13_rc as release

def canonical(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()

def write_json(path, change):
    obj = json.loads(path.read_bytes())
    change(obj)
    path.write_bytes(canonical(obj))

def flip_signature(root):
    path = root / "release/agent-manifest.sig.json"
    obj = json.loads(path.read_bytes())
    raw = bytearray(release.unb64(obj["signature"]))
    raw[-1] ^= 1
    obj["signature"] = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    path.write_bytes(canonical(obj))

def manifest_digest_without_resigning(root):
    path = root / "release/agent-manifest.json"
    obj = json.loads(path.read_bytes())
    obj["files"][0]["sha256"] = "0" * 64
    path.write_bytes(canonical(obj))
    write_json(root / "release/agent-manifest.sig.json",
               lambda envelope: envelope.update(manifest_sha256=release.sha(path.read_bytes())))

def private_jwk(root):
    write_json(root / "release/release-signing-public.jwk",
               lambda key: key.update(d="unsigned-fixture-private-field"))

def symlink_agent(root):
    path = root / "agent/linux.py"
    path.unlink()
    path.symlink_to(release.BUNDLE / "agent/linux.py")

def snapshot():
    paths = [release.APP / "public" / rel for rel in release.FILESET]
    paths += [release.BUNDLE / rel for rel in (*release.FILESET, *release.EXTRA)]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

def main():
    before = snapshot()
    baseline = release.verify_bundle(release.BUNDLE)
    operations = []
    for rel in release.FILESET:
        def mutate(root, rel=rel):
            path = root / rel
            path.write_bytes(path.read_bytes() + b"\n")
        operations.append(("payload_tamper:" + rel, mutate))
    operations += [
        ("manifest_unsigned_version", lambda root:
            write_json(root / "release/agent-manifest.json",
                       lambda obj: obj.update(agent_version="0.3.54"))),
        ("manifest_rebound_digest_no_resign", manifest_digest_without_resigning),
        ("signature_bit_flip", flip_signature),
        ("signature_algorithm", lambda root:
            write_json(root / "release/agent-manifest.sig.json",
                       lambda obj: obj.update(alg="HS256"))),
        ("signature_kid", lambda root:
            write_json(root / "release/agent-manifest.sig.json",
                       lambda obj: obj.update(kid="untrusted-fixture-key"))),
        ("public_modulus_tamper", lambda root:
            write_json(root / "release/release-signing-public.jwk",
                       lambda obj: obj.update(n="AA"))),
        ("public_private_field_denied", private_jwk),
        ("checksum_index_tamper", lambda root:
            (root / "release/SHA256SUMS").write_bytes(b"0  agent/linux.py\n")),
        ("symlink_leaf_denied", symlink_agent),
    ]
    assert len(operations) == 13
    checks = []
    with tempfile.TemporaryDirectory(prefix="commander-full053-unsigned-guards-", dir="/tmp_hara") as temp:
        parent = Path(temp)
        for index, (name, mutate) in enumerate(operations):
            root = parent / str(index)
            shutil.copytree(release.BUNDLE, root)
            mutate(root)
            try:
                release.verify_bundle(root, compare_active=False)
            except release.ValidationError as exc:
                checks.append({"name": name, "state": "DENIED", "code": str(exc)})
            else:
                raise AssertionError("FULL053_UNSIGNED_TAMPER_ACCEPTED:" + name)
    assert before == snapshot(), "FULL053_SOURCE_OR_FROZEN_BUNDLE_MUTATED"
    print(json.dumps({
        "schema": "hara.commander-full053-unsigned-tamper-guards.v1",
        "state": "PASS", "checks": len(checks), "passed_checks": checks,
        "manifest_sha256": baseline["manifest_sha256"],
        "all_platform_versions_match_manifest": True,
        "source_and_frozen_bundle_unchanged": True,
        "signing_performed": False, "private_key_accessed": False,
        "production_action_executed": False,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
