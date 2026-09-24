#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
PUBLIC = APP / "public"
LINUX = (PUBLIC / "install/linux.sh").read_text(encoding="utf-8")
WINDOWS = (PUBLIC / "install/windows.ps1").read_text(encoding="utf-8")
INDEX = (PUBLIC / "index.html").read_text(encoding="utf-8")
APP_JS = (PUBLIC / "app.js").read_text(encoding="utf-8")
MANIFEST_PATH = PUBLIC / "release/agent-manifest.json"

LINUX_BOOTSTRAP = (
    "curl -fsS --proto '=https' --tlsv1.2 --location --max-redirs 0 "
    "https://commander.haralabs.com.br/install/linux.sh | bash"
)
WINDOWS_BOOTSTRAP = (
    "irm https://commander.haralabs.com.br/install/windows.ps1 "
    "-MaximumRedirection 0 | iex"
)
SUMS_PATH = PUBLIC / "release/SHA256SUMS"
DRIFT = (APP / "scripts/validate_prod_runtime_drift.py").read_text(encoding="utf-8")

EXPECTED = (
    "agent/linux.py",
    "agent/windows.ps1",
    "install/linux.sh",
    "install/windows.ps1",
)

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SUPPLY_CHAIN_{code}=FAIL")
    print(f"COMMANDER_SUPPLY_CHAIN_{code}=PASS")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    proc = subprocess.run(
        ["python3", "apps/commander/scripts/build_release_manifest.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    need(proc.returncode == 0, "RELEASE_MANIFEST_GENERATOR")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    need(manifest.get("schema") == "hara.commander-agent-release.v1", "MANIFEST_SCHEMA")
    entries = {str(x.get("path")): x for x in manifest.get("files", [])}
    need(tuple(entries.keys()) == EXPECTED, "MANIFEST_EXACT_FILE_SET")

    sums = SUMS_PATH.read_text(encoding="utf-8")
    for rel in EXPECTED:
        path = PUBLIC / rel
        digest = sha(path)
        entry = entries[rel]
        code = rel.upper().replace("/", "_").replace(".", "_")
        need(entry.get("sha256") == digest, "MANIFEST_SHA_" + code)
        need(int(entry.get("bytes", -1)) == path.stat().st_size, "MANIFEST_SIZE_" + code)
        need(f"{digest}  {rel}\n" in sums, "SUMS_" + code)

    need('BASE_URL="${HARA_COMMANDER_URL:-https://commander.haralabs.com.br}"' in LINUX, "LINUX_DEFAULT_HTTPS")
    need('"https://commander.haralabs.com.br"' in WINDOWS, "WINDOWS_DEFAULT_HTTPS")
    need("http://" not in LINUX and "http://" not in WINDOWS, "NO_PLAINTEXT_HTTP")
    need("--insecure" not in LINUX and " -k" not in LINUX, "LINUX_TLS_BYPASS_ABSENT")
    need("-SkipCertificateCheck" not in WINDOWS, "WINDOWS_TLS_BYPASS_ABSENT")

    need(LINUX_BOOTSTRAP in INDEX and LINUX_BOOTSTRAP in APP_JS, "LINUX_BOOTSTRAP_UI_COPY_PARITY")
    need(WINDOWS_BOOTSTRAP in INDEX and WINDOWS_BOOTSTRAP in APP_JS, "WINDOWS_BOOTSTRAP_UI_COPY_PARITY")
    need("curl -fsSL https://commander.haralabs.com.br/install/linux.sh | bash" not in INDEX + APP_JS,
         "LINUX_BOOTSTRAP_REDIRECT_DEFAULT_ABSENT")
    need("irm https://commander.haralabs.com.br/install/windows.ps1 | iex" not in INDEX + APP_JS,
         "WINDOWS_BOOTSTRAP_REDIRECT_DEFAULT_ABSENT")
    need("--proto '=https'" in LINUX_BOOTSTRAP and "--tlsv1.2" in LINUX_BOOTSTRAP,
         "LINUX_BOOTSTRAP_TLS_PIN")
    need("--location --max-redirs 0" in LINUX_BOOTSTRAP,
         "LINUX_BOOTSTRAP_REDIRECT_DENIED")
    need("-MaximumRedirection 0" in WINDOWS_BOOTSTRAP,
         "WINDOWS_BOOTSTRAP_REDIRECT_DENIED")

    need("/release/agent-manifest.json" in LINUX, "LINUX_MANIFEST_FETCH")
    need("AGENT_SHA256_MISMATCH" in LINUX, "LINUX_SHA_ENFORCEMENT")
    need("AGENT_VERSION_MANIFEST_MISMATCH" in LINUX, "LINUX_VERSION_ENFORCEMENT")
    need("--self-test" in LINUX, "LINUX_SELF_TEST")

    need("/release/agent-manifest.json" in WINDOWS, "WINDOWS_MANIFEST_FETCH")
    need("AGENT_SHA256_MISMATCH" in WINDOWS, "WINDOWS_SHA_ENFORCEMENT")
    need("AGENT_VERSION_MANIFEST_MISMATCH" in WINDOWS, "WINDOWS_VERSION_ENFORCEMENT")
    need("Assert-AgentIntegrity" in WINDOWS, "WINDOWS_INTEGRITY_FUNCTION")

    for public_path in (
        "/install/linux.sh",
        "/install/windows.ps1",
        "/agent/linux.py",
        "/agent/windows.ps1",
        "/release/agent-manifest.json",
        "/release/SHA256SUMS",
    ):
        need(public_path in DRIFT, "RUNTIME_DRIFT_" + public_path.upper().replace("/", "_").replace(".", "_"))

    need("Assert-AgentSelfTest" in WINDOWS, "WINDOWS_SELF_TEST_FUNCTION")
    need(WINDOWS.count("Assert-AgentSelfTest $") >= 2, "WINDOWS_SELF_TEST_INSTALL_AND_UPDATE")
    need("AGENT_SELF_TEST_FAILED" in WINDOWS, "WINDOWS_SELF_TEST_FAIL_CLOSED")

    print("COMMANDER_BOOTSTRAP_INITIAL_TRUST=WEB_ORIGIN")
    print("COMMANDER_BOOTSTRAP_INDEPENDENT_TRUST_ANCHOR=PENDING_MATURITY")
    print("COMMANDER_AGENT_POST_BOOTSTRAP_INTEGRITY=PASS")
    print("COMMANDER_RELEASE_RUNTIME_ATTESTATION=READY")
    print("COMMANDER_SUPPLY_CHAIN=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
