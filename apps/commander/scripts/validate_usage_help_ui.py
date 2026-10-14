#!/usr/bin/env python3
"""Regression checks for customer Usage, Settings and Help UI.

Read-only. No HTTP, Cloudflare, billing or customer-data access.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
PUB=ROOT/"apps/commander/public"
html=(PUB/"index.html").read_text(encoding="utf-8")
js=(PUB/"app.js").read_text(encoding="utf-8")
css=(PUB/"styles.css").read_text(encoding="utf-8")

def section(name: str, successor: str) -> str:
    start=f'<section class="view app-view" data-view="{name}"'
    nxt=f'<section class="view app-view" data-view="{successor}"'
    assert html.count(start)==1, f"SECTION_{name}_MISSING"
    return html.split(start,1)[1].split(nxt,1)[0]

usage=section("usage","plans")
plans=section("plans","connections")
security=section("security","help")
help_page=html.split('<section class="view app-view" data-view="help"',1)[1].split("</main>",1)[0]

assert usage.count('<div class="quota-meta"')==1
meta=usage.split('<div class="quota-meta"',1)[1].split("</div>",1)[0]
assert meta.count("<span>")==1, "USAGE_META_MUST_ONLY_HAVE_PERIOD"
assert '<small>Período</small>' in meta and 'id="usagePeriod"' in meta
assert "Métrica" not in usage and "Repetições" not in usage
assert "Sem dupla contagem" not in usage
assert usage.count('class="summary-card')==4, "USAGE_FOUR_STATS_PRESERVED"
for id in ("usageCardTransactions","usageCardCapacity","usageCardPlan","usageCardPeriod"):
    assert f'id="{id}"' in usage, id
assert "Franquia de execuções do plano" in usage
assert "O que este contador mede:" in usage
assert 'data-billing-plan="STANDARD"' in plans, "PLANS_INTACT"
assert 'data-billing-portal' in plans, "BILLING_ACTION_INTACT"

assert security.count('class="panel settings-card')==5, "SETTINGS_FIVE_CARDS"
assert security.count('class="panel settings-card full-panel"')==1
for name in ("Identidade","Conteúdo do cliente","Acesso atual","Status do Commander"):
    assert name in security,name
assert 'data-submit-local-support' not in security, "HELP_NOT_REMOVED_FROM_SETTINGS"
assert "Enviar diagnóstico" in help_page
assert help_page.count("data-submit-local-support")==1
assert help_page.count('id="supportReportStatus"')==1
assert 'href="https://www.haralabs.com.br/support/"' in help_page
assert "role=\"status\" aria-live=\"polite\"" in help_page

nav=html.split('<template id="sidebarTemplate">',1)[1].split("</template>",1)[0]
assert nav.count('data-app-go=')==5
assert nav.index('data-app-go="help"')>nav.index('data-app-go="security"')
assert 'class="sidebar-help-action"' in nav
assert '"help"' in js and 'help: "Ajuda · HARA Commander"' in js
assert "submitLocalSupportReport(submitLocalSupport)" in js
assert 'event.target.closest("[data-app-go]")' in js
assert 'data-view="help" aria-labelledby="help-title"' in html
assert "app.js?v=20261014-wordmark1" in html
assert "styles.css?v=20261014-usage-help-ui-v1" in html
for scope in ('[data-view="usage"] .workspace-main','[data-view="security"] .settings-grid','[data-view="help"] .workspace-main'):
    assert scope in css,scope
assert "repeat(5,minmax(0,1fr))" in css, "HELP_MOBILE_NAV_FIVE_ITEMS"
assert "min-height:calc(100dvh - 74px)" in css, "VERTICAL_CENTERING"
assert ".settings-card dl>div" in css, "SETTINGS_DIVIDER_SCOPE"
assert "border:0;padding:5px 0;" in css, "SETTINGS_DIVIDERS_REMOVED"
print("COMMANDER_USAGE_HELP_LAYOUT=PASS")
print("COMMANDER_USAGE_DUPLICATED_META=0")
print("COMMANDER_SETTINGS_ALIGNED_CARDS=5")
print("COMMANDER_HELP_SIDEBAR_NAV=PASS")
print("COMMANDER_BILLING_STRUCTURE=UNCHANGED")
print("COMMANDER_CSS_DESKTOP_MOBILE=READY")
