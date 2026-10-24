#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "apps" / "commander" / "scripts" / "commander_local_first_unit_economics.py"


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_UNIT_ECONOMICS_{code}=FAIL")
    print(f"COMMANDER_UNIT_ECONOMICS_{code}=PASS")


source = SCRIPT.read_text(encoding="utf-8")
need("FREE_MONTHLY_CALL_LIMIT = 10_000" in source, "FREE_10K")
need("LOCAL_BUDGET_BLOCK_UNITS = 100" in source, "BLOCK_100")
need("OLD_QUOTA_RPCS_PER_GOVERNED_CALL = 2" in source, "LEGACY_TWO_RPC")
need('"quota_plane_rpc_reduction_percent"' in source, "REDUCTION_MODELED")
need('"O1_FALLBACK"' in source, "O1_FALLBACK")
need('"NOT_MODELED_REQUIRES_LIVE_ANALYTICS"' in source, "NO_FAKE_USD")

proc = subprocess.run(
    ["python3", str(SCRIPT), "--check"],
    cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    timeout=20, check=False,
)
need(proc.returncode == 0, "CHECK_EXIT")
need("COMMANDER_FREE_10K_LEGACY_QUOTA_RPCS=20000" in proc.stdout, "FREE_10K_OLD_RPC")
need("COMMANDER_FREE_10K_LOCAL_BUDGET_BLOCKS_MAX=100" in proc.stdout, "FREE_10K_BLOCKS")
need("COMMANDER_FREE_10K_QUOTA_RPC_REDUCTION_PERCENT=99.5" in proc.stdout, "FREE_10K_REDUCTION")
print("COMMANDER_LOCAL_FIRST_UNIT_ECONOMICS_CONTRACT=PASS")
