#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
PUBLIC=APP/"public"
BOOT=(PUBLIC/"bootstrap/linux-dual-origin.sh").read_text(encoding="utf-8")
LINUX=(PUBLIC/"install/linux.sh").read_bytes()
KEY=(PUBLIC/"release/release-signing-public.jwk").read_bytes()

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_BOOTSTRAP_DUAL_ORIGIN_{code}=FAIL")
    print(f"COMMANDER_BOOTSTRAP_DUAL_ORIGIN_{code}=PASS")

m=re.search(r'HARA_BOOTSTRAP_TRUST_COMMIT="([0-9a-f]{40})"',BOOT)
need(bool(m),"PINNED_COMMIT")
commit=m.group(1)

need("raw.githubusercontent.com/tiagoharalabs/hara-site/" in BOOT,"GITHUB_INDEPENDENT_ORIGIN")
need("${HARA_BOOTSTRAP_TRUST_COMMIT}/apps/commander/public" in BOOT,"GITHUB_IMMUTABLE_PATH")
need("--proto \'=https\'" in BOOT and "--tlsv1.2" in BOOT,"TLS_REQUIRED")
need("--max-redirs 0" in BOOT,"REDIRECT_DENIED")
need('cmp -s "$hara_installer" "$github_installer"' in BOOT,"INSTALLER_EXACT_COMPARE")
need('cmp -s "$hara_key" "$github_key"' in BOOT,"RELEASE_KEY_EXACT_COMPARE")
need("HARA_BOOTSTRAP_INSTALLER_ORIGIN_MISMATCH=TRUE" in BOOT,"INSTALLER_FAIL_CLOSED")
need("HARA_BOOTSTRAP_RELEASE_KEY_ORIGIN_MISMATCH=TRUE" in BOOT,"KEY_FAIL_CLOSED")
need('bash "$hara_installer" "$@"' in BOOT,"EXECUTES_ONLY_VERIFIED_PRIMARY")
need("HARA_BOOTSTRAP_DUAL_ORIGIN=PASS" in BOOT,"PASS_ATTESTATION")
need('"${1:-}" = "--verify-only"' in BOOT and "HARA_BOOTSTRAP_VERIFY_ONLY=PASS" in BOOT,"VERIFY_ONLY_MODE")

show=subprocess.run(
    ["git","show",f"{commit}:apps/commander/public/install/linux.sh"],
    cwd=ROOT,capture_output=True,check=False,
)
need(show.returncode==0,"PINNED_INSTALLER_EXISTS")
need(hashlib.sha256(show.stdout).digest()==hashlib.sha256(LINUX).digest(),"PINNED_INSTALLER_MATCHES_CURRENT")

show_key=subprocess.run(
    ["git","show",f"{commit}:apps/commander/public/release/release-signing-public.jwk"],
    cwd=ROOT,capture_output=True,check=False,
)
need(show_key.returncode==0,"PINNED_KEY_EXISTS")
need(hashlib.sha256(show_key.stdout).digest()==hashlib.sha256(KEY).digest(),"PINNED_KEY_MATCHES_CURRENT")

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    fakebin=root/"bin"; fakebin.mkdir()
    curl=fakebin/"curl"
    curl.write_text("""#!/usr/bin/env bash
set -eu
url=""
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    http*) url="$1"; shift ;;
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "$url" in
  */install/linux.sh)
    if [[ "$url" == *raw.githubusercontent.com* ]]; then printf 'SECOND' > "$out"; else printf 'FIRST' > "$out"; fi ;;
  */release/release-signing-public.jwk) printf 'KEY' > "$out" ;;
  *) exit 7 ;;
esac
""")
    curl.chmod(0o755)
    env=os.environ.copy()
    env["PATH"]=str(fakebin)+":/usr/bin:/bin"
    env["HARA_COMMANDER_URL"]="https://commander.haralabs.com.br"
    proc=subprocess.run(["bash",str(PUBLIC/"bootstrap/linux-dual-origin.sh")],cwd=ROOT,env=env,text=True,capture_output=True)
    need(proc.returncode==20 and "HARA_BOOTSTRAP_INSTALLER_ORIGIN_MISMATCH=TRUE" in proc.stderr,"TAMPER_DENIED")

print("COMMANDER_BOOTSTRAP_DUAL_ORIGIN=PASS")
