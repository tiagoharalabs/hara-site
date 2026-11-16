#!/usr/bin/env python3
"""Offline, unprivileged container canary. NOT installer/systemd/pairing acceptance."""
import base64
import hashlib
import hmac
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

SIGNED = pathlib.Path(os.environ.get("HARA_QA_RELEASE_ROOT", "/qa/signed"))
TESTS = pathlib.Path(os.environ.get("HARA_QA_TEST_ROOT", "/qa/test"))
V = "0.3.84"
AGENT_SHA = "2177b4d6e049e5886a1df6a42c38ca0a1838e4e7406536882e81eaa2c8c2d509"
ORIGINAL_SHA = "a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733"
MANIFEST_SHA = "b0350ec8dc9f2b995742cf07df91df8ad5aaa324a9948b16753f178cef2820fe"
SIGNATURE_SHA = "e0bc91232b7cb9f5344a1cd000dcb7e9a6be1e6b6c634c911626414bee31fe15"
PUBLIC_SHA = "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b"
PINNED = {
    "agent/linux.py": AGENT_SHA,
    "agent/windows.ps1": "5b331dfbb9be9c36bb8b54194dea73a85e79789273965d288ab64b47b907aff0",
    "install/linux.sh": "e9a203ae3fdda1d6cc55e857bc0cf471a1e5d738a0b9ccab9526aef692b03476",
    "install/windows.ps1": "6208f5ab9f7d71b7c91472cb9f9ce3c3c70305213bfea515e24ddddbeac937c6",
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def check(condition, label):
    if not condition:
        raise RuntimeError("QA_HOLD:" + label)

def source(path):
    info = path.lstat()
    check(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1, "REGULAR_SOURCE")
    check(info.st_size <= 2 * 1024 * 1024, "SOURCE_SIZE")
    raw = path.read_bytes()
    check(len(raw) == info.st_size, "SOURCE_CHANGED")
    return raw

def read_signed(name):
    return source(SIGNED / name)

def strict_b64(value):
    check(type(value) is str and len(value) > 0, "B64_TYPE")
    result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    check(base64.urlsafe_b64encode(result).decode().rstrip("=") == value, "B64_CANONICAL")
    return result

def verify_release():
    manifest_raw = read_signed("release/agent-manifest.json")
    signature_raw = read_signed("release/agent-manifest.sig.json")
    public_raw = read_signed("release/release-signing-public.jwk")
    check(sha(manifest_raw) == MANIFEST_SHA, "MANIFEST_PIN")
    check(sha(signature_raw) == SIGNATURE_SHA, "SIGNATURE_PIN")
    check(sha(public_raw) == PUBLIC_SHA, "PUBLIC_PIN")
    manifest = json.loads(manifest_raw)
    signature = json.loads(signature_raw)
    key = json.loads(public_raw)
    check(manifest.get("agent_version") == V and manifest.get("schema") == "hara.commander-agent-release.v1", "MANIFEST_VERSION")
    check(signature.get("kid") == key.get("kid") == "commander-release-v2", "KID")
    check(signature.get("alg") == key.get("alg") == "RS256", "ALG")
    check(signature.get("manifest_sha256") == MANIFEST_SHA, "SIGNATURE_BIND")
    check(key.get("kty") == "RSA" and not any(x in key for x in ("d", "p", "q", "dp", "dq", "qi")), "PRIVATE_KEY_FORBIDDEN")
    rows = manifest.get("files")
    check(type(rows) is list and len(rows) == 4 and {x["path"] for x in rows} == set(PINNED), "FOUR_FILES")
    for row in rows:
        raw = read_signed(row["path"])
        check(len(raw) == row["bytes"] and sha(raw) == row["sha256"] == PINNED[row["path"]], "ARTIFACT_SHA_" + row["path"])
    sums = read_signed("release/SHA256SUMS").decode()
    check(sums == "".join(value + "  " + name + "\n" for name, value in PINNED.items()), "SUMS")
    n = int.from_bytes(strict_b64(key["n"]), "big")
    e = int.from_bytes(strict_b64(key["e"]), "big")
    raw_sig = strict_b64(signature["signature"])
    width = (n.bit_length() + 7) // 8
    check(width == len(raw_sig) == 384 and e == 65537, "RSA3072")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(manifest_raw).digest()
    expected = b"\0\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\0" + digest_info
    actual = pow(int.from_bytes(raw_sig, "big"), e, n).to_bytes(width, "big")
    check(hmac.compare_digest(expected, actual), "RSA_SIGNATURE")
    check(json.loads(read_signed("PRIVATE-QA-VERIFICATION.json"))["signature_verified"] is True, "RELEASE_REPORT")
    check(not any("private" in str(x).lower() and x.suffix == ".jwk" for x in SIGNED.rglob("*")), "NO_PRIVATE_KEY")
    return True

def run_py(path, args, env):
    p = subprocess.run([sys.executable, "-I", "-B", str(path)] + list(args), text=True, capture_output=True, env=env, timeout=38)
    if p.returncode:
        raise RuntimeError("QA_COMMAND_FAILED:" + str(path.name) + ":" + str(p.returncode) + ":" + p.stderr[-160:])
    return p.stdout

def swap(target, data):
    temp = target.with_name("." + target.name + ".qa-atomic")
    check(not temp.exists(), "TEMP_COLLISION")
    with temp.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temp.chmod(0o700)
    os.replace(temp, target)
    check(stat.S_IMODE(target.stat().st_mode) == 0o700, "POST_MODE")
    return sha(source(target))

def main():
    check(os.geteuid() != 0, "NONROOT_REQUIRED")
    status = pathlib.Path("/proc/self/status").read_text()
    check("NoNewPrivs:\t1" in status, "NO_NEW_PRIVS_REQUIRED")
    cap = [x for x in status.splitlines() if x.startswith("CapEff:")][0].split()[1]
    check(int(cap, 16) == 0, "CAPABILITIES_PRESENT")
    check(not pathlib.Path("/proc/net/route").read_text().splitlines()[1:], "NETWORK_ROUTE_PRESENT")
    check(verify_release(), "RELEASE_VERIFY")
    original = source(TESTS / "agent.original.py")
    check(sha(original) == ORIGINAL_SHA, "ORIGINAL_SHA")
    checks = ["RSA3072_SIGNATURE_AND_FOUR_SHA_PASS", "OFFLINE_NO_CAPABILITIES_PASS"]
    with tempfile.TemporaryDirectory(prefix="hara-0384-container-") as td:
        root = pathlib.Path(td)
        home = root / "qa-home"
        home.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / ".local/share"), XDG_CONFIG_HOME=str(home / ".config"))
        installed = home / ".local/share/hara-commander/hara-commander-agent"
        installed.parent.mkdir(mode=0o700, parents=True)
        backup = root / "backup-agent"
        installed.write_bytes(original)
        installed.chmod(0o700)
        backup.write_bytes(original)
        backup.chmod(0o600)
        check(run_py(installed, ["--version"], env).strip() == "0.3.83", "BASELINE_VERSION")
        checks.append("ORIGINAL_0383_BASELINE_PASS")
        changed = bytearray(read_signed("agent/linux.py"))
        changed[-1] ^= 1
        check(sha(changed) != AGENT_SHA and sha(source(installed)) == ORIGINAL_SHA, "TAMPER_HOLD")
        checks.append("NEGATIVE_TAMPER_FAIL_CLOSED")
        check(swap(installed, read_signed("agent/linux.py")) == AGENT_SHA, "UPDATE_SHA")
        check(run_py(installed, ["--version"], env).strip() == V, "CANDIDATE_VERSION")
        selftest = run_py(installed, ["--self-test"], env)
        check("COMMANDER_LOCAL_MCP_TOOL_COUNT=41" in selftest and "COMMANDER_ARBITRARY_FUNCTION=DENIED" in selftest, "CANDIDATE_SELF_TEST")
        checks.append("ISOLATED_CANDIDATE_0384_SELFTEST_41_PASS")
        # Test exactly the signed .84 Agent, using the separately pinned .83 preimage.
        scriptroot = root / "sources"
        scriptroot.mkdir()
        (scriptroot / "agent.candidate.r2.py").write_bytes(read_signed("agent/linux.py"))
        (scriptroot / "agent.original.py").write_bytes(original)
        env["HARA_MODEFIX_SOURCE_DIR"] = str(scriptroot)
        result = json.loads(run_py(TESTS / "test_modefix_r2.py", [], env))
        check(result["state"] == "PASS" and result["total"] == 14, "MODE_REGRESSION")
        check(result["positive_gid"] is False, "UNPRIVILEGED_GID_EXPECTED")
        checks.append("R2_MODES_XATTR_FAILURE_CASES_PASS")
        acl = json.loads(run_py(TESTS / "test_modefix_acl_r2.py", [], env))
        check(acl["state"] == "PASS_POSIX_ACL_EXACT" and acl["xattr_count"] >= 1, "ACL_REGRESSION")
        checks.append("POSIX_ACL_EXACT_PASS")
        check(swap(installed, source(backup)) == ORIGINAL_SHA, "ROLLBACK_SHA")
        check(run_py(installed, ["--version"], env).strip() == "0.3.83", "ROLLBACK_VERSION")
        check(not (home / ".config/hara-commander/device.env").exists(), "NO_ENROLLMENT")
        checks.append("OFFLINE_FILE_SWAP_AND_ROLLBACK_PASS")
    print(json.dumps({"state": "OFFLINE_CONTAINER_CANARY_PASS", "version": V,
        "checks": checks, "checks_passed": len(checks), "rsa3072": True,
        "operational_scope": "EPHEMERAL_NO_NETWORK_USERSPACE_ONLY",
        "native_installer_e2e": False, "systemd_user_tested": False,
        "pairing_tested": False, "production_mutated": False,
        "original_sha256": ORIGINAL_SHA, "candidate_sha256": AGENT_SHA}, sort_keys=True))

if __name__ == "__main__":
    main()
