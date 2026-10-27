#!/usr/bin/env python3
"""Sign the exact .56 four-file candidate for PRIVATE QA; never deploy it.

Only a new directory outside the repository is written. Artifact, manifest and
public-key pins are fixed: no caller-supplied replacement pins or key generation.
The manifest's existing stable channel is retained for installer compatibility;
neither a valid signature nor this program grants public-release acceptance.
Event V2 OFF is the intended QA scope, not an assertion about a running Agent.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import resource
import stat
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

VERSION = "0.3.56"
KID = "commander-release-v2"
MANIFEST_SHA256 = "fd8fef20c54fd805d8837a665334ac5c075289545b5d66b7fbaac1954a16f56a"
PUBLIC_SHA256 = "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b"
ARTIFACT_SHA256 = {
    "agent/linux.py": "ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d",
    "agent/windows.ps1": "a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620",
    "install/linux.sh": "a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f",
    "install/windows.ps1": "2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401",
}
PRIVATE_FIELDS = {"d", "p", "q", "dp", "dq", "qi", "oth"}
REPORT = "PRIVATE-QA-VERIFICATION.json"
FILE_LIMIT = 2 * 1024 * 1024


class SigningError(Exception):
    """Only fixed, nonsensitive codes are exposed by the command line."""


def need(ok, code):
    if not ok:
        raise SigningError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def strict_json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            need(key not in obj, "JSON_DUPLICATE_KEY")
            obj[key] = value
        return obj
    def constant(_value):
        raise SigningError("JSON_NONFINITE_VALUE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (ValueError, UnicodeError):
        raise SigningError("JSON_INVALID") from None


def absolute_path(value):
    path = Path(value)
    need(path.is_absolute() and ".." not in path.parts, "ABSOLUTE_PATH_REQUIRED")
    return path


def check_parents(path, private=False):
    for parent in reversed(path.parents):
        s = parent.lstat()
        need(stat.S_ISDIR(s.st_mode), "PARENT_NOT_DIRECTORY_OR_SYMLINK")
        if private:
            need(s.st_uid in (0, os.geteuid()), "PRIVATE_PARENT_OWNER")
            sticky_root = s.st_uid == 0 and bool(s.st_mode & stat.S_ISVTX)
            need(not (s.st_mode & 0o022) or sticky_root, "PRIVATE_PARENT_WRITABLE")


def identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
            s.st_uid, s.st_gid, s.st_mode, s.st_nlink)


def read_exact(path, limit=FILE_LIMIT, private=False):
    path = absolute_path(path)
    check_parents(path, private=private)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
             "INPUT_NOT_BOUNDED_REGULAR_FILE")
        if private:
            need(before.st_uid == os.geteuid() and
                 stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1,
                 "PRIVATE_KEY_CUSTODY")
        chunks = []
        count = 0
        while True:
            block = os.read(fd, min(65536, limit + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            need(count <= limit, "INPUT_TOO_LARGE")
        raw = b"".join(chunks)
        need(len(raw) == before.st_size and identity(os.fstat(fd)) == identity(before)
             and identity(path.lstat()) == identity(before), "INPUT_CHANGED")
        return raw
    finally:
        os.close(fd)


def unb64(text):
    need(type(text) is str and 0 < len(text) <= 16384 and
         re.fullmatch(r"[A-Za-z0-9_-]+", text) is not None, "JWK_OR_SIGNATURE_ENCODING")
    raw = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)
    need(base64.urlsafe_b64encode(raw).decode().rstrip("=") == text,
         "JWK_OR_SIGNATURE_NONCANONICAL")
    return raw


def integer(text):
    raw = unb64(text)
    need(len(raw) <= 1024 and raw[0] != 0, "JWK_INTEGER_INVALID")
    return int.from_bytes(raw, "big")


def public_key(raw):
    need(sha(raw) == PUBLIC_SHA256, "PUBLIC_PIN_MISMATCH")
    obj = strict_json(raw)
    need(type(obj) is dict and obj.get("kty") == "RSA" and
         obj.get("alg") == "RS256" and obj.get("kid") == KID and
         not PRIVATE_FIELDS.intersection(obj), "PUBLIC_JWK_INVALID")
    key = rsa.RSAPublicNumbers(integer(obj["e"]), integer(obj["n"])).public_key()
    need(key.key_size >= 2048, "PUBLIC_RSA_TOO_SMALL")
    return obj, key


def validate_inputs(source, manifest_raw, public_raw):
    need(sha(manifest_raw) == MANIFEST_SHA256, "MANIFEST_PIN_MISMATCH")
    manifest = strict_json(manifest_raw)
    need(type(manifest) is dict and set(manifest) ==
         {"schema", "product", "channel", "agent_version", "files"} and
         manifest["schema"] == "hara.commander-agent-release.v1" and
         manifest["product"] == "H.A.R.A. Commander" and
         manifest["channel"] == "stable" and manifest["agent_version"] == VERSION,
         "MANIFEST_CONTRACT")
    rows = manifest["files"]
    need(type(rows) is list and len(rows) == len(ARTIFACT_SHA256), "MANIFEST_FILESET")
    blobs = {}
    for row in rows:
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"},
             "MANIFEST_ROW")
        name = row["path"]
        need(type(name) is str and name in ARTIFACT_SHA256 and name not in blobs,
             "MANIFEST_FILESET")
        need(type(row["bytes"]) is int and 0 < row["bytes"] <= FILE_LIMIT and
             row["sha256"] == ARTIFACT_SHA256[name], "MANIFEST_ARTIFACT_PIN")
        raw = read_exact(source / name)
        need(len(raw) == row["bytes"] and sha(raw) == ARTIFACT_SHA256[name],
             "ARTIFACT_BYTES_MISMATCH")
        blobs[name] = raw
    need(set(blobs) == set(ARTIFACT_SHA256), "MANIFEST_FILESET")
    public, key = public_key(public_raw)
    for name, prefix in (("install/linux.sh", "RELEASE_SIGNING_"),
                         ("install/windows.ps1", r"\$ReleaseSigning")):
        text = blobs[name].decode("utf-8-sig")
        for field, linux_name, windows_name in (("kid", "KID", "Kid"),
                                               ("n", "N", "N"), ("e", "E", "E")):
            suffix = linux_name if name.endswith(".sh") else windows_name
            found = re.findall(r"(?m)^" + prefix + suffix + r'\s*=\s*"([^"\r\n]+)"\s*$', text)
            need(found == [public[field]], "INSTALLER_PUBLIC_PIN_MISMATCH")
    return blobs, public, key


def make_signature(manifest_raw, public, key, private_path):
    # The key necessarily exists in process memory; del is not secure erasure.
    # Disable dumps in this short-lived signer before reading any private bytes.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    need(resource.getrlimit(resource.RLIMIT_CORE) == (0, 0), "SIGNER_CORE_DUMPS_NOT_DISABLED")
    raw = read_exact(private_path, limit=65536, private=True)
    private = strict_json(raw)
    need(type(private) is dict and private.get("kty") == "RSA" and
         private.get("alg") == "RS256" and private.get("kid") == KID and
         private.get("n") == public["n"] and private.get("e") == public["e"] and
         "oth" not in private and all(k in private for k in ("d", "p", "q", "dp", "dq", "qi")),
         "PRIVATE_PUBLIC_KEY_MISMATCH")
    private_key = rsa.RSAPrivateNumbers(
        p=integer(private["p"]), q=integer(private["q"]), d=integer(private["d"]),
        dmp1=integer(private["dp"]), dmq1=integer(private["dq"]), iqmp=integer(private["qi"]),
        public_numbers=key.public_numbers()).private_key()
    signature = private_key.sign(manifest_raw, padding.PKCS1v15(), hashes.SHA256())
    key.verify(signature, manifest_raw, padding.PKCS1v15(), hashes.SHA256())
    del raw, private, private_key
    return encoded({"alg": "RS256", "kid": KID,
                    "manifest_sha256": sha(manifest_raw),
                    "schema": "hara.commander-release-signature.v1",
                    "signature": base64.urlsafe_b64encode(signature).decode().rstrip("=")})


def verify_signature(manifest_raw, signature_raw, key):
    obj = strict_json(signature_raw)
    need(type(obj) is dict and set(obj) ==
         {"alg", "kid", "manifest_sha256", "schema", "signature"} and
         obj["alg"] == "RS256" and obj["kid"] == KID and
         obj["schema"] == "hara.commander-release-signature.v1" and
         obj["manifest_sha256"] == sha(manifest_raw), "SIGNATURE_CONTRACT")
    signature = unb64(obj["signature"])
    numbers = key.public_numbers()
    width = (numbers.n.bit_length() + 7) // 8
    need(len(signature) == width and int.from_bytes(signature, "big") < numbers.n,
         "SIGNATURE_RANGE")
    try:
        key.verify(signature, manifest_raw, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise SigningError("SIGNATURE_INVALID") from None
    # Also match the installer's raw RSA/PKCS#1 v1.5 verification convention.
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(manifest_raw).digest()
    expected = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    actual = pow(int.from_bytes(signature, "big"), numbers.e, numbers.n).to_bytes(width, "big")
    need(hmac.compare_digest(actual, expected), "INSTALLER_RSA_VERIFY_FAILED")


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    need(read_exact(path) == raw, "OUTPUT_READBACK_MISMATCH")


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_stage_path(repo, stage, must_be_new=False):
    repo = absolute_path(repo)
    stage = absolute_path(stage)
    check_parents(repo)
    need(stat.S_ISDIR(repo.lstat().st_mode), "REPOSITORY_NOT_DIRECTORY")
    need(stage != repo and repo not in stage.parents, "OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    check_parents(stage, private=True)
    if must_be_new:
        need(not os.path.lexists(stage), "OUTPUT_ALREADY_EXISTS")
    else:
        s = stage.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid() and
             stat.S_IMODE(s.st_mode) == 0o700, "OUTPUT_NOT_PRIVATE")
    return stage


def verify_stage(repo, stage):
    stage = private_stage_path(repo, stage)
    expected = {"agent": {"linux.py", "windows.ps1"},
                "install": {"linux.sh", "windows.ps1"},
                "release": {"agent-manifest.json", "agent-manifest.sig.json",
                            "release-signing-public.jwk", "SHA256SUMS"}}
    need(set(os.listdir(stage)) in (set(expected), set(expected) | {REPORT}), "OUTPUT_FILESET")
    for directory, names in expected.items():
        folder = stage / directory
        need(stat.S_ISDIR(folder.lstat().st_mode) and set(os.listdir(folder)) == names,
             "OUTPUT_FILESET")
    manifest = read_exact(stage / "release/agent-manifest.json", 65536)
    public_raw = read_exact(stage / "release/release-signing-public.jwk", 65536)
    blobs, _public, key = validate_inputs(stage, manifest, public_raw)
    signature = read_exact(stage / "release/agent-manifest.sig.json", 65536)
    verify_signature(manifest, signature, key)
    sums = "".join(f"{ARTIFACT_SHA256[n]}  {n}\n" for n in ARTIFACT_SHA256).encode()
    need(read_exact(stage / "release/SHA256SUMS") == sums, "SUMS_MISMATCH")
    return {"schema": "hara.commander-private-qa-signature-check.v1",
            "status": "PRIVATE_QA_SIGNATURE_AND_FOUR_ARTIFACTS_VERIFIED",
            "version": VERSION, "kid": KID, "rsa_bits_observed": key.key_size,
            "manifest_sha256": sha(manifest), "public_jwk_sha256": sha(public_raw),
            "signature_sha256": sha(signature),
            "artifacts": {n: {"bytes": len(b), "sha256": sha(b)} for n, b in blobs.items()},
            "intended_event_v2": "OFF", "runtime_activation_verified": False,
            "signature_verified": True, "native_acceptance": False,
            "installation_performed": False, "release_approval": False,
            "production_mutated": False, "private_key_exported": False}


def sign_stage(repo, source, manifest_path, public_path, private_path, stage):
    stage = private_stage_path(repo, stage, must_be_new=True)
    source = absolute_path(source)
    manifest = read_exact(manifest_path, 65536)
    public_raw = read_exact(public_path, 65536)
    blobs, public, key = validate_inputs(source, manifest, public_raw)
    signature = make_signature(manifest, public, key, absolute_path(private_path))
    verify_signature(manifest, signature, key)
    # Every source was read, pinned and verified before creating any output.
    # Failure leaves a private partial directory for inspection; no overwrite or retry cleanup.
    os.mkdir(stage, 0o700)
    for name in ("agent", "install", "release"):
        os.mkdir(stage / name, 0o700)
    for name, raw in blobs.items():
        write_new(stage / name, raw)
    write_new(stage / "release/agent-manifest.json", manifest)
    write_new(stage / "release/release-signing-public.jwk", public_raw)
    write_new(stage / "release/SHA256SUMS", "".join(
        f"{ARTIFACT_SHA256[n]}  {n}\n" for n in ARTIFACT_SHA256).encode())
    write_new(stage / "release/agent-manifest.sig.json", signature)
    report = verify_stage(repo, stage)
    write_new(stage / REPORT, encoded(report))
    for folder in (stage / "agent", stage / "install", stage / "release", stage, stage.parent):
        fsync_directory(folder)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sign", "verify"))
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--public-jwk", type=Path)
    parser.add_argument("--private-jwk", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "sign":
            need(all((args.source_root, args.manifest, args.public_jwk, args.private_jwk)),
                 "SIGN_INPUTS_REQUIRED")
            report = sign_stage(args.repo_root, args.source_root, args.manifest,
                                args.public_jwk, args.private_jwk, args.output_dir)
        else:
            need(not any((args.source_root, args.manifest, args.public_jwk, args.private_jwk)),
                 "VERIFY_USES_ONLY_PINNED_STAGE")
            report = verify_stage(args.repo_root, args.output_dir)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except SigningError as error:
        print("PRIVATE_QA_SIGNING_HOLD=" + str(error), file=sys.stderr)
    except Exception:
        # Never include a library exception, JWK, raw input or key path in logs.
        print("PRIVATE_QA_SIGNING_HOLD=INPUT_OR_CRYPTO_OPERATION_FAILED", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
