#!/usr/bin/env python3
"""Build one pinned, unsigned 0.3.59 private-QA candidate in a new directory.

No network, credentials, signing, installation, or public deployment. Linux
inputs receive their exact version-only transforms. The separately reviewed
Windows .59 Agent and installer are admitted by immutable input/output pins.
No source file is modified; frozen .56/.57 releases stay untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

VERSION = "0.3.59"
PREVIOUS = b"0.3.56"
CURRENT = VERSION.encode("ascii")
PUBLIC_SHA256 = "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b"
SOURCE_PINS = {
    "agent/linux.py": "ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d",
    "agent/windows.ps1": "d3a4173829186e2488c2b686f5ac3ecca62c896387f55dcdfdbcdd155253ae24",
    "install/linux.sh": "f9489f8c4647644c72ef507bd7a6dc50a11306b0e9f7858e6e424e696e4bb272",
    "install/windows.ps1": "2f734ab8066b46cb82fc4fc9fb25244472bc829c16043cfe5f2771ae4e6d04b4",
}
CONTROLLER_PINS = {
    "linux/commander_connect.py": "a696a233e81b1b89b536fd4097af7b571762c953e54266cba49349308db74c1d",
    "windows/Connect-Commander.ps1": "2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da",
}
REPLACEMENT_COUNTS = {"agent/linux.py": 1, "install/linux.sh": 8}
VERSIONED_WINDOWS_COUNTS = {"agent/windows.ps1": 1, "install/windows.ps1": 5}
OUTPUT_PINS = {
    "agent/linux.py": "df8b2d09c5447f8d405200538a841e669a8f165e9043701d6c8efcbfe5a34d38",
    "agent/windows.ps1": "d3a4173829186e2488c2b686f5ac3ecca62c896387f55dcdfdbcdd155253ae24",
    "install/linux.sh": "80732c941725e06f317ef42e878a0498d30f28bf890dd07d9a0b6a90f0cd0581",
    "install/windows.ps1": "2f734ab8066b46cb82fc4fc9fb25244472bc829c16043cfe5f2771ae4e6d04b4",
}
MANIFEST_SHA256 = "efe39839596883875358cfc27cd7ec62c0d38acc3c03708df56034a82d35d7b4"
FILE_LIMIT = 2 * 1024 * 1024


class BuildError(Exception):
    """Only fixed diagnostic codes are printed."""


def need(condition, code):
    if not condition:
        raise BuildError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def absolute(value):
    path = Path(value)
    need(path.is_absolute() and ".." not in path.parts, "ABSOLUTE_PATH_REQUIRED")
    return path


def check_parents(path, private=False):
    for parent in reversed(path.parents):
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode), "PARENT_NOT_DIRECTORY_OR_SYMLINK")
        if private:
            need(info.st_uid in (0, os.geteuid()), "PRIVATE_PARENT_OWNER")
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            need(not (info.st_mode & 0o022) or sticky_root, "PRIVATE_PARENT_WRITABLE")


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_uid, info.st_gid, info.st_mode, info.st_nlink)


def read_pinned(path, expected):
    path = absolute(path)
    check_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= FILE_LIMIT,
             "INPUT_NOT_BOUNDED_REGULAR_FILE")
        chunks = []
        count = 0
        while True:
            block = os.read(fd, min(65536, FILE_LIMIT + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            need(count <= FILE_LIMIT, "INPUT_TOO_LARGE")
        raw = b"".join(chunks)
        need(len(raw) == before.st_size and
             identity(os.fstat(fd)) == identity(before) and
             identity(path.lstat()) == identity(before), "INPUT_CHANGED")
        need(sha(raw) == expected, "INPUT_PIN_MISMATCH")
        return raw
    finally:
        os.close(fd)


def version_only(name, raw):
    need(raw.count(PREVIOUS) == REPLACEMENT_COUNTS[name], "VERSION_LITERAL_COUNT_CHANGED")
    need(CURRENT not in raw, "TARGET_VERSION_ALREADY_PRESENT")
    if name.startswith("agent/"):
        anchor = (rb'^AGENT_VERSION = "0\.3\.56"\r?$' if name.endswith(".py")
                  else rb'^\$AgentVersion = "0\.3\.56"\r?$')
        need(len(re.findall(anchor, raw, re.M)) == 1, "AGENT_VERSION_ANCHOR_CHANGED")
    updated = raw.replace(PREVIOUS, CURRENT)
    need(len(updated) == len(raw) and PREVIOUS not in updated and
         updated.replace(CURRENT, PREVIOUS) == raw, "VERSION_TRANSFORM_NOT_REVERSIBLE")
    return updated


def controller_blocks(controllers):
    linux = controllers["linux/commander_connect.py"]
    windows = controllers["windows/Connect-Commander.ps1"]
    start = b"$ErrorActionPreference='Stop'"
    end = b"\nif($MyInvocation.InvocationName -ne '.'){"
    need(windows.count(start) == 1 and windows.count(end) == 1,
         "WINDOWS_CONTROLLER_MARKERS_CHANGED")
    core = windows[windows.index(start):windows.index(end)]
    need(PREVIOUS not in linux and PREVIOUS not in core,
         "CONTROLLER_CONTAINS_RELEASE_VERSION")
    return {"install/linux.sh": linux, "install/windows.ps1": core}


def validate_output_path(output, source056, connect_source):
    check_parents(output, private=True)
    need(not os.path.lexists(output), "OUTPUT_ALREADY_EXISTS")
    for source in (source056, connect_source):
        need(output != source and source not in output.parents, "OUTPUT_INSIDE_SOURCE")
        for parent in (source, *source.parents):
            if os.path.lexists(parent / ".git"):
                need(output != parent and parent not in output.parents,
                     "OUTPUT_INSIDE_REPOSITORY")
    # A separately specified output must not land in an unrelated checkout.
    need(not any(os.path.lexists(parent / ".git") for parent in output.parents),
         "OUTPUT_INSIDE_REPOSITORY")


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def build(source056, connect_source, windows_source, public_path, output):
    source056, connect_source, windows_source, public_path, output = map(
        absolute, (source056, connect_source, windows_source, public_path, output))
    validate_output_path(output, source056, connect_source)
    validate_output_path(output, source056, windows_source)
    paths = {
        "agent/linux.py": source056 / "agent/linux.py",
        "agent/windows.ps1": windows_source / "windows-agent.ps1",
        "install/linux.sh": connect_source / "linux/linux.source-only-candidate.sh",
        "install/windows.ps1": windows_source / "windows.source-only-candidate.ps1",
    }
    inputs = {name: read_pinned(path, SOURCE_PINS[name]) for name, path in paths.items()}
    controllers = {name: read_pinned(connect_source / name, pin)
                   for name, pin in CONTROLLER_PINS.items()}
    public = read_pinned(public_path, PUBLIC_SHA256)
    public_obj = json.loads(public)
    need(public_obj.get("kid") == "commander-release-v2" and
         public_obj.get("alg") == "RS256" and public_obj.get("kty") == "RSA" and
         not {"d", "p", "q", "dp", "dq", "qi", "oth"}.intersection(public_obj),
         "PUBLIC_JWK_CONTRACT_CHANGED")
    outputs = {}
    for name, raw in inputs.items():
        if name in REPLACEMENT_COUNTS:
            outputs[name] = version_only(name, raw)
        else:
            need(name in VERSIONED_WINDOWS_COUNTS and raw.count(CURRENT) == VERSIONED_WINDOWS_COUNTS[name]
                 and PREVIOUS not in raw and b"0.3.57" not in raw and b"0.3.58" not in raw,
                 "REVIEWED_WINDOWS_VERSION_CONTRACT_CHANGED")
            if name == "agent/windows.ps1":
                need(len(re.findall(rb'^\$AgentVersion = "0\.3\.59"\r?$', raw, re.M)) == 1,
                     "REVIEWED_WINDOWS_AGENT_VERSION_ANCHOR_CHANGED")
            outputs[name] = raw
        need(sha(outputs[name]) == OUTPUT_PINS[name], "OUTPUT_ARTIFACT_PIN_MISMATCH")
    blocks = controller_blocks(controllers)
    for name, block in blocks.items():
        need(inputs[name].count(block) == 1 and outputs[name].count(block) == 1,
             "EMBEDDED_CONTROLLER_CHANGED")
        need(b"# HARA_COMMANDER_PAIR_EXISTING=1\n" in outputs[name],
             "PAIR_EXISTING_CAPABILITY_MISSING")
    need(b"# HARA_COMMANDER_REENROLL=1\n" in outputs["install/windows.ps1"],
         "REENROLL_CAPABILITY_MISSING")
    manifest = encoded({
        "agent_version": VERSION, "channel": "stable",
        "files": [{"bytes": len(raw), "path": name, "sha256": sha(raw)}
                  for name, raw in outputs.items()],
        "product": "H.A.R.A. Commander", "schema": "hara.commander-agent-release.v1",
    })
    need(sha(manifest) == MANIFEST_SHA256, "OUTPUT_MANIFEST_PIN_MISMATCH")
    files = dict(outputs)
    files["release/agent-manifest.json"] = manifest
    files["release/release-signing-public.jwk"] = public
    files["release/SHA256SUMS"] = "".join(f"{sha(raw)}  {name}\n" for name, raw in outputs.items()).encode()
    report = {
        "schema": "hara.commander.private-0359-build.v1",
        "state": "UNSIGNED_PRIVATE_QA_CANDIDATE_BUILT", "version": VERSION,
        "input_artifacts": {name: {"sha256": sha(raw), "bytes": len(raw)}
                            for name, raw in inputs.items()},
        "version_replacement_counts": REPLACEMENT_COUNTS,
        "version_only_transform": False,
        "linux_version_only_transform": True,
        "windows_reviewed_source_admitted_unchanged": True,
        "embedded_controllers_unchanged": True,
        "controller_pins": CONTROLLER_PINS,
        "artifacts": {name: {"sha256": sha(raw), "bytes": len(raw)}
                      for name, raw in outputs.items()},
        "manifest_sha256": sha(manifest), "public_jwk_sha256": sha(public),
        "unsigned": True, "signature_created": False, "native_acceptance": False,
        "existing_signed_release_modified": False, "installation_performed": False,
        "production_mutated": False, "private_keys_read": False,
    }
    files["BUILD-REPORT.json"] = encoded(report)
    # All inputs and transforms have been verified before the first write.
    # A later failure leaves the new private directory for inspection; no reset.
    os.mkdir(output, 0o700)
    for folder in ("agent", "install", "release"):
        os.mkdir(output / folder, 0o700)
    for name, raw in files.items():
        write_new(output / name, raw)
    for name, raw in files.items():
        need(read_pinned(output / name, sha(raw)) == raw, "OUTPUT_READBACK_FAILED")
    for folder in (output / "agent", output / "install", output / "release", output, output.parent):
        fsync_directory(folder)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source056", required=True, type=Path)
    parser.add_argument("--connect-source", required=True, type=Path)
    parser.add_argument("--windows-source", required=True, type=Path)
    parser.add_argument("--public-jwk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build(args.source056, args.connect_source, args.windows_source, args.public_jwk, args.output)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except BuildError as error:
        print(json.dumps({"state": "BUILD_REFUSED", "code": str(error)}))
        return 2
    except Exception as error:
        print(json.dumps({"state": "BUILD_FAILED", "code": "PRIVATE_QA_BUILD_FAILED",
                          "exception_type": type(error).__name__}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
