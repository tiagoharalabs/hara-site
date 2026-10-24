#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
LINUX = (APP / "public" / "agent" / "linux.py").read_text(encoding="utf-8")
WINDOWS = (APP / "public" / "agent" / "windows.ps1").read_text(encoding="utf-8")
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
PROBE = APP / "scripts" / "commander_operational_slo.py"


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_OPERATIONAL_SLO_{code}=FAIL")
    print(f"COMMANDER_OPERATIONAL_SLO_{code}=PASS")


for source, label in ((LINUX, "LINUX"), (WINDOWS, "WINDOWS")):
    need("INTERNAL_BETA_V1" in source, label + "_PROFILE")
    need("99.0" in source, label + "_SUCCESS_TARGET")
    need("6000" in source and "12000" in source, label + "_TAIL_TARGETS")
    need("5000" in source, label + "_BOUNDED_SAMPLE")
    need("latency_p50_ms" in source and "latency_p95_ms" in source and "latency_p99_ms" in source, label + "_PERCENTILES")
    need("latency_sample_size" in source and "latency_sample_capped" in source, label + "_SAMPLE_METADATA")
    need("INSUFFICIENT_DATA" in source and "DEGRADED" in source, label + "_STATES")

need("latency_p50_ms:" in WORKER and "latency_p95_ms:" in WORKER and "latency_p99_ms:" in WORKER, "WORKER_SANITIZER")
need('profile:"INTERNAL_BETA_V1"' in WORKER, "WORKER_PROFILE")
need("Math.max(...percentileValues.p95)" in WORKER, "TENANT_CONSERVATIVE_P95")
need("slo:local.slo || cloud.slo" in WORKER, "FALLBACK_PRESERVES_SLO")
need(PROBE.is_file(), "PROBE_PRESENT")

proc = subprocess.run(
    ["python3", str(PROBE), "--self-test"],
    cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    timeout=20, check=False,
)
need(proc.returncode == 0 and "COMMANDER_OPERATIONAL_SLO_SELFTEST=PASS" in proc.stdout, "PROBE_SELFTEST")

print("COMMANDER_OPERATIONAL_SLO_CONTRACT=PASS")
