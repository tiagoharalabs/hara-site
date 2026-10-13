#!/usr/bin/env python3
"""Private unsigned release guards: staged tamper, scope, and immutable-target refusal."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import build_commander_windows_051_v11_rc as release

def main():
    original = release.APP / "public"
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (original/"agent/linux.py", original/"install/linux.sh",
                        original/"install/windows.ps1", original/"agent/windows.ps1")}
    checks = []
    def denied(code, operation):
        try:
            operation()
        except (RuntimeError, release.signer.ReleaseError) as err:
            if code not in str(err):
                raise
            checks.append(code)
        else:
            raise AssertionError("EXPECTED_DENIAL_MISSING:"+code)
    with tempfile.TemporaryDirectory(prefix="commander-win51-unsigned-test-") as temp:
        root = Path(temp)
        stage = root/"stage"
        original_new = release.NEW
        release.NEW = root/"immutable51"
        try:
            release.prepare(stage)
            release.validate_stage_source(stage)
            checks.append("UNTAMPERED_UNSIGNED_STAGE_ACCEPTED")
            pub = stage/"apps/commander/public"
            if (pub/"release/agent-manifest.sig.json").exists():
                raise AssertionError("UNSIGNED_STAGE_HAS_SIGNATURE")
            checks.append("NO_SIGNATURE_OR_KEY_OPERATION")
            for rel in release.FILESET:
                path = pub/rel
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw+b"\n")
                    denied("STAGING_SOURCE_DRIFT:"+rel, lambda: release.validate_stage_source(stage))
                finally:
                    path.write_bytes(raw)
                release.validate_stage_source(stage)
            for rel, error in (("release/agent-manifest.json","STAGING_MANIFEST_DRIFT"),
                               ("release/release-signing-public.jwk","STAGING_KEY_DRIFT"),
                               ("release/SHA256SUMS","STAGING_CHECKSUM_DRIFT")):
                path = pub/rel
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw+b"\n")
                    denied(error, lambda: release.validate_stage_source(stage))
                finally:
                    path.write_bytes(raw)
                release.validate_stage_source(stage)
            denied("IMMUTABLE_RELEASE_TARGET_EXISTS", lambda: release.prepare(stage))
            release.NEW.mkdir()
            denied("IMMUTABLE_RELEASE_TARGET_EXISTS", lambda: release.prepare(root/"second-stage"))
            release.validate_stage_source(stage)
            checks.append("REJECTED_MUTATIONS_PRESERVE_REVIEWED_STAGE")
        finally:
            release.NEW = original_new
    after = {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in before}
    if before != after:
        raise AssertionError("SOURCE_OR_LINUX_COMPONENT_MODIFIED")
    checks.append("SOURCE_INSTALLER_AND_LINUX_PRESERVED")
    print(json.dumps({"schema":"hara.commander-windows051-unsigned-release-guards.v1",
                      "state":"PASS","checks":len(checks),"passed_checks":checks,
                      "source_sha256":release.APPROVED_SOURCE_SHA256,
                      "historical_frozen_source":True,"active_source_claim":False,
                      "signing_performed":False,"production_action_executed":False},sort_keys=True))

if __name__ == "__main__":
    main()
