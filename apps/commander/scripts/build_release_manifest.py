#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import os
import shutil
import tempfile
import base64
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
PUBLIC = APP / "public"
RELEASE_DIR = PUBLIC / "release"
MANIFEST = RELEASE_DIR / "agent-manifest.json"
SUMS = RELEASE_DIR / "SHA256SUMS"
FILES = (
    "agent/linux.py",
    "agent/windows.ps1",
    "install/linux.sh",
    "install/windows.ps1",
)
SCHEMA = "hara.commander-agent-release.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError("RELEASE_SOURCE_SYMLINK")
    blobs = {}
    for rel in FILES:
        path = root / rel
        if not path.is_file() or path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("RELEASE_FILE_MISSING_OR_SYMLINK:" + rel)
        blobs[rel] = path.read_bytes()
        if not 0 < len(blobs[rel]) <= 2 * 1024 * 1024:
            raise ValueError("RELEASE_FILE_SIZE:" + rel)
    return blobs


def agent_version(blobs: dict[str, bytes] | None = None) -> str:
    blobs = snapshot(PUBLIC) if blobs is None else blobs
    l = re.findall(r'^AGENT_VERSION\s*=\s*"([^"\r\n]+)"\s*$', blobs[FILES[0]].decode("utf-8"), re.M)
    w = re.findall(r'^\$AgentVersion\s*=\s*"([^"\r\n]+)"\s*$', blobs[FILES[1]].decode("utf-8"), re.M)
    if len(l) != 1 or len(w) != 1:
        raise SystemExit("AGENT_VERSION_NOT_FOUND")
    if l[0] != w[0]:
        raise SystemExit("AGENT_VERSION_MISMATCH")
    if not re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', l[0]):
        raise ValueError("AGENT_VERSION_INVALID")
    for rel, pattern in (
        (FILES[2], r'["\x27]agent_version["\x27]\s*:\s*["\x27]([0-9.]+)["\x27]'),
        (FILES[3], r'\bagent_version\s*=\s*"([0-9.]+)"'),
    ):
        versions = re.findall(pattern, blobs[rel].decode("utf-8"), re.I)
        extra = re.findall(r'if version!="([0-9.]+)"', blobs[rel].decode()) if rel.endswith('linux.sh') else re.findall(r'\$manifest\.agent_version -cne "([0-9.]+)"', blobs[rel].decode())
        versions += extra
        if not versions or any(v != l[0] for v in versions):
            raise ValueError("INSTALLER_AGENT_VERSION_MISMATCH:" + rel)
    return l[0]


def render(blobs: dict[str, bytes] | None = None) -> tuple[str, str]:
    blobs = snapshot(PUBLIC) if blobs is None else blobs
    version = agent_version(blobs)
    files = []
    for rel in FILES:
        files.append({
            "bytes": len(blobs[rel]),
            "path": rel,
            "sha256": hashlib.sha256(blobs[rel]).hexdigest(),
        })
    payload = {
        "agent_version": version,
        "channel": "stable",
        "files": files,
        "product": "H.A.R.A. Commander",
        "schema": SCHEMA,
    }
    manifest_text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    sums_text = "".join(f"{item['sha256']}  {item['path']}\n" for item in files)
    return manifest_text, sums_text


def validate_trust_anchors(blobs: dict[str, bytes]) -> None:
    """Check the existing pinned v2 public key in both installer sources."""
    for rel, names in (
        (FILES[2], ("RELEASE_SIGNING_KID", "RELEASE_SIGNING_N", "RELEASE_SIGNING_E")),
        (FILES[3], (r"\$ReleaseSigningKid", r"\$ReleaseSigningN", r"\$ReleaseSigningE")),
    ):
        values = []
        for name in names:
            found = re.findall(r'^' + name + r'\s*=\s*"([^"\r\n]+)"\s*$', blobs[rel].decode(), re.M)
            if len(found) != 1:
                raise ValueError("INSTALLER_TRUST_ANCHOR:" + rel)
            values.append(found[0])
        kid, n, e = values
        modulus = base64.urlsafe_b64decode(n + "=" * (-len(n) % 4))
        exponent = base64.urlsafe_b64decode(e + "=" * (-len(e) % 4))
        if kid != "commander-release-v2" or len(modulus) != 384 or e != "AQAB" or \
           hashlib.sha256(modulus + b":" + exponent).hexdigest() != \
           "e235a64f0e89490a597cdb0a6c20cc1c7bf68f6ea5f5e88c6f80a48cf11b601b":
            raise ValueError("INSTALLER_TRUST_ANCHOR:" + rel)


def build_candidate(source: Path, output: Path, policy: dict, *, draft: bool = False) -> dict:
    """Snapshot/copy all four admitted source bytes together; never sign or bump."""
    required_status = "SOURCE_ADAPTATION_PROPOSED" if draft else "SOURCE_ADAPTION_REVIEWED"
    required_classification = "commercial-candidate" if draft else "commercial"
    if policy.get("schema") != "hara.commander-commercial-source-review.v1" or \
       policy.get("status") != required_status or \
       set(policy.get("artifacts") or {}) != set(FILES):
        raise ValueError("COMMERCIAL_SOURCE_REVIEW_REQUIRED")
    blobs = snapshot(source)
    version = agent_version(blobs)
    # The existing schema has one version for both platforms. .55 is the
    # minimum common version; .54 Linux + .55 Windows needs a new schema.
    if tuple(map(int, version.split("."))) < (0, 3, 55):
        raise ValueError("COMMON_VERSION_BELOW_FLOOR")
    if version != policy.get("version"):
        raise ValueError("SOURCE_VERSION_NOT_REVIEWED")
    for rel, blob in blobs.items():
        row = policy["artifacts"][rel]
        if row.get("classification") != required_classification or not row.get("review_reference") or \
           not re.fullmatch(r"[0-9a-f]{40}", row.get("source_commit", "")) or \
           row.get("sha256") != hashlib.sha256(blob).hexdigest():
            raise ValueError("SOURCE_PROVENANCE_OR_DIGEST:" + rel)
    validate_trust_anchors(blobs)
    manifest, sums = render(blobs)
    if output.exists() or output.is_symlink() or \
       output.parent.resolve() != output.parent.absolute():
        raise ValueError("CANDIDATE_DESTINATION_UNSAFE_OR_EXISTS")
    work = Path(tempfile.mkdtemp(prefix=".commander-unsigned-", dir=output.parent))
    try:
        for rel, blob in blobs.items():
            path = work / rel
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(blob)
        (work / "release").mkdir()
        (work / "release/agent-manifest.json").write_bytes(manifest.encode("utf-8"))
        (work / "release/SHA256SUMS").write_bytes(sums.encode("utf-8"))
        key_path = Path(__file__).resolve().parents[3] / "scripts/fixtures/commercial_v2_043_signature/release-signing-public.jwk"
        key_raw = key_path.read_bytes()
        if hashlib.sha256(key_raw).hexdigest() != "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b":
            raise ValueError("PUBLIC_TRUST_ANCHOR_NOT_PINNED")
        (work / "release/release-signing-public.jwk").write_bytes(key_raw)
        if snapshot(source) != blobs:
            raise ValueError("SOURCE_CHANGED_DURING_BUILD")
        result = {"state": "UNSIGNED_DRAFT_REQUIRES_ADMISSION" if draft else "UNSIGNED_CANDIDATE_NOT_RELEASE_APPROVAL", "version": version,
                  "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
                  "artifact_count": 4, "signature_issued": False, "published": False}
        (work / "candidate.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
        os.rename(work, output)
        work = None
        return result
    finally:
        if work is not None:
            shutil.rmtree(work)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-policy", type=Path)
    parser.add_argument("--draft", action="store_true", help="build proposed sources for review only; never admits or signs them")
    args = parser.parse_args()
    if not args.check:
        if not (args.source_dir and args.output and args.source_policy):
            parser.error("unsigned build requires --source-dir --output --source-policy; public/ is never overwritten")
        try:
            policy = json.loads(args.source_policy.read_text(encoding="utf-8"))
            print(json.dumps(build_candidate(args.source_dir, args.output, policy, draft=args.draft), sort_keys=True))
            return 0
        except (ValueError, OSError) as exc:
            print("COMMANDER_CANDIDATE_HOLD=" + str(exc), file=sys.stderr)
            return 2
    if args.source_dir or args.output or args.source_policy or args.draft:
        parser.error("--check reads the checkout public/ only")
    manifest_text, sums_text = render()
    if args.check:
        if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != manifest_text:
            print("COMMANDER_RELEASE_MANIFEST=STALE", file=sys.stderr)
            return 1
        if not SUMS.is_file() or SUMS.read_text(encoding="utf-8") != sums_text:
            print("COMMANDER_RELEASE_SHA256SUMS=STALE", file=sys.stderr)
            return 1
        print("COMMANDER_RELEASE_MANIFEST=PASS")
        print("COMMANDER_RELEASE_SHA256SUMS=PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
