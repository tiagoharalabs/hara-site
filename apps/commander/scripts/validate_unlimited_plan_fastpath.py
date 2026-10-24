#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
WORKER=(ROOT/"apps/commander/src/worker.js").read_text(encoding="utf-8")
APP=(ROOT/"apps/commander/public/app.js").read_text(encoding="utf-8")

def need(ok, code):
    if not ok:
        raise SystemExit("COMMANDER_UNLIMITED_FASTPATH_"+code+"=FAIL")
    print("COMMANDER_UNLIMITED_FASTPATH_"+code+"=PASS")

need("function unlimitedProductUsage()" in WORKER, "HELPER")
need('period_key: "UNLIMITED"' in WORKER and "metered: false" in WORKER, "CONTRACT")
need('if (kind === "NONE") return { ...unlimitedProductUsage(), available: true };' in WORKER, "NONE_BYPASS")
helper=WORKER.split("async function productUsageForPolicy",1)[1].split("async function dashboard",1)[0]
need(helper.index('if (kind === "NONE")') < helper.index("TENANT_QUOTA.getByName"), "BYPASS_BEFORE_DO")
dashboard=WORKER.split("async function dashboard(env",1)[1].split("async function dashboardForSubject",1)[0]
portal=WORKER.split("async function dashboardForSubject",1)[1].split("async function grantsForPlan",1)[0]
usage=WORKER.split("async function customerUsage",1)[1].split("async function recentCustomerCalls",1)[0]
need("productUsageForPolicy" in dashboard and "TENANT_QUOTA.getByName" not in dashboard, "DEV_DASHBOARD")
need("productUsageForPolicy" in portal and "TENANT_QUOTA.getByName" not in portal, "PORTAL_DASHBOARD")
need("productUsageForPolicy" in usage and "TENANT_QUOTA.getByName" not in usage, "MCP_USAGE")
need('"Ilimitado"' in APP and '"Sem limite"' in APP, "UNLIMITED_UI")
need("Dados da conta não atualizados" not in APP, "STALE_LOGIN_BANNER_ABSENT")
need("Sua sessão continua ativa." in APP and "Atualizar dados" in APP, "DEGRADED_COPY")
need('"USAGE_TEMPORARILY_UNAVAILABLE"' in WORKER and "available: false" in WORKER, "METERED_READ_DEGRADE")
need("Quota reserve/commit/release paths remain fail-closed" in WORKER, "EXECUTION_FAIL_CLOSED_COMMENT")
need("Uso temporariamente indisponível" in APP and "Plano, sessão e computadores continuam disponíveis" in APP, "PARTIAL_UI")
print("COMMANDER_UNLIMITED_PLAN_FASTPATH=PASS")
