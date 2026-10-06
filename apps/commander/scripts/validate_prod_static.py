#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CFG = json.loads((APP / "wrangler.jsonc").read_text())
WORKER = (APP / "src/worker.js").read_text()
CUSTOMER_MCP = (APP / "src/customer-mcp.mjs").read_text()
SIMPLE_MCP = (APP / "src/customer-mcp-simple.mjs").read_text()
DEVICE_TARGETING = (APP / "src/device-targeting.mjs").read_text()
AUTH = (APP / "src/auth.js").read_text()
HTML = (APP / "public/index.html").read_text()
JS = (APP / "public/app.js").read_text()
CSS = (APP / "public/styles.css").read_text()
LINUX = (APP / "public/install/linux.sh").read_text()
WINDOWS = (APP / "public/install/windows.ps1").read_text()
HEADERS = (APP / "public/_headers").read_text()
READBACK = (APP / "scripts/commander_prod_readback.py").read_text()
TRIAL_MIGRATION = (APP / "migrations/0008_trial_onboarding.sql").read_text()
COMMERCIAL_MIGRATION = (APP / "migrations/0021_commercial_terms_20261005.sql").read_text()
APPROVAL_MODE_MIGRATION = (APP / "migrations/0017_device_approval_mode.sql").read_text()

def need(ok, code):
    if not ok:
        raise AssertionError(code)

need(CFG["name"] == "hara-commander", "WORKER_NAME")
need(CFG["vars"]["ENVIRONMENT"] == "PROD", "ENVIRONMENT")
need(CFG["vars"]["STORAGE_MODE"] == "REMOTE_PROD", "STORAGE_MODE")
need(CFG["vars"]["AUTH_CLIENT_AUTH"] == "BASIC", "AUTH_CLIENT_AUTH")
need(CFG["d1_databases"][0]["database_name"] == "hara-commander-product-prod", "PROD_D1_NAME")
need(CFG["d1_databases"][0]["database_id"] == "2c6473ff-9f65-4ee3-b9aa-a68996d47c46", "PROD_D1_ID")
need(CFG["routes"][0] == {"pattern": "commander.haralabs.com.br", "custom_domain": True}, "PROD_ROUTE")
need('"DEV", "PROD"' in WORKER, "RUNTIME_ENV_GATE")
need('url.pathname.startsWith("/api/dev/")' in WORKER, "DEV_PREFIX_GATE")
need(
    'if (url.pathname === "/api/dev/health" && request.method === "GET") {' in WORKER
    and 'requireRemoteDevToken(request, env);' in WORKER,
    "DEV_HEALTH_TOKEN_GUARD",
)
need('requireDev(env)' in WORKER, "DEV_REQUIRE_GATE")
need('url.pathname === "/api/health"' in WORKER, "PROD_HEALTH")
health_block = WORKER.split('if (url.pathname === "/api/health" && request.method === "GET") {', 1)[1].split('if (url.pathname === "/api/dev/health"', 1)[0]
need('environment:' not in health_block and 'storage_mode:' not in health_block and 'auth:' not in health_block, "PUBLIC_HEALTH_METADATA_MINIMIZED")
auth_config_block = WORKER.split('if (url.pathname === "/api/portal/auth-config" && request.method === "GET") {', 1)[1].split('if (url.pathname === "/auth/login"', 1)[0]
need('return json({ configured: authStatus(env).configured });' in auth_config_block and 'provider:' not in auth_config_block and 'client_auth:' not in auth_config_block, "PUBLIC_AUTH_CONFIG_MINIMIZED")
need('DEV_ENDPOINT_DISABLED: 404' in WORKER, "DEV_DISABLED_STATUS")
need("auth-bootstrap-pending" in HTML, "AUTH_FIRST_PAINT")
need(
    'data-approval-choice="always"' in HTML
    and 'data-approval-choice="ask"' in HTML
    and 'HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED' in HTML
    and 'let installApprovalMode = "PERSISTENT_TRUSTED"' in JS
    and 'hara-commander doctor' in HTML
    and 'setInstallApprovalMode' in JS
    and 'installCommandLinux' in JS
    and 'installCommandWindows' in JS,
    "APPROVAL_MODE_ONBOARDING",
)
need(
    "ADD COLUMN approval_mode TEXT NOT NULL DEFAULT 'ASK_EVERY_ACTION'" in APPROVAL_MODE_MIGRATION
    and 'idx_commander_devices_approval_mode' in APPROVAL_MODE_MIGRATION,
    "APPROVAL_MODE_MIGRATION",
)
need("styles.css?v=20261006-productusage1" in HTML, "STYLE_CACHE_KEY")
need("app.js?v=20261006-productusage1" in HTML, "SCRIPT_CACHE_KEY")
need('./brand/chatgpt-official.webp' in HTML and (APP / "public/brand/chatgpt-official.webp").stat().st_size > 0, "CHATGPT_BRAND_ICON")
need('./brand/claude-official.svg' in HTML and (APP / "public/brand/claude-official.svg").stat().st_size > 0, "CLAUDE_BRAND_ICON")
need('class="where-badge">AI</span><p><b>ChatGPT' not in HTML and 'class="where-badge">AI</span><p><b>Claude' not in HTML, "CLIENT_PLACEHOLDER_BADGES_REMOVED")
need(
    'class="neon-toggle"' in HTML
    and 'class="neon-icon"' in HTML
    and 'localStorage.getItem("hara-neon")' in HTML
    and 'const neonBtn = document.querySelector(".neon-toggle")' in JS
    and 'localStorage.setItem("hara-neon", next)' in JS
    and 'html[data-neon="on"] .neon-toggle' in CSS
    and 'H.A.R.A Neon bolt control' in CSS,
    "NEON_BOLT_APPEARANCE_MODE",
)
need(
    "0 6px 18px rgba(218,156,19,.20)" in CSS
    and "drop-shadow(0 0 5px rgba(240,184,46,.84))" in CSS,
    "NEON_ON_VISIBLE_GLOW",
)
need(
    "H.A.R.A Neon theme color contract v3" in CSS
    and "rgba(57,162,223,.86)" in CSS
    and "rgba(255,200,61,.86)" in CSS,
    "NEON_THEME_COLOR_CONTRACT",
)
need(
    "H.A.R.A Neon identity emphasis v4" in CSS
    and "drop-shadow(0 0 12px rgba(57,162,223,.34))" in CSS
    and "0 0 12px rgba(57,162,223,.24)" in CSS,
    "NEON_LIGHT_IDENTITY_GLOW",
)
need(
    "H.A.R.A Commander Neon final glow contract v5" in CSS
    and 'html[data-neon="off"] .neon-toggle' in CSS
    and "rgba(57,162,223,.90)" in CSS
    and "rgba(255,200,61,.90)" in CSS,
    "COMMANDER_NEON_FINAL_GLOW_CONTRACT",
)
need(
    "H.A.R.A Commander light-theme blue coherence v6" in CSS
    and "background:#2f9fd8" in CSS
    and "background:linear-gradient(135deg,#0f6f9f,#174f76)" in CSS
    and "drop-shadow(0 0 16px rgba(57,162,223,.46))" in CSS,
    "COMMANDER_LIGHT_BLUE_COHERENCE",
)
need(
    "H.A.R.A Commander active-nav surface lock v7" in CSS
    and 'html[data-theme="light"][data-neon="off"] .side-nav button.active' in CSS
    and 'html[data-theme="light"][data-neon="on"] .side-nav button.active' in CSS
    and "background:linear-gradient(90deg,#0d3d5f,#0b304a)" in CSS,
    "COMMANDER_ACTIVE_NAV_SURFACE_LOCK",
)
need('const apiBase = localHost' in JS and ': location.origin;' in JS, "PROD_API_OVERRIDE_BLOCKED")
need('const scenario = localHost' in JS, "PROD_SCENARIO_OVERRIDE_BLOCKED")
need('appViews.has(requested) && !sessionAuthenticated' in JS, "PROTECTED_ROUTE_GUARD")
need('route("login", false);' in JS and 'location.pathname + "#login"' in JS, "AUTH_ERROR_VIEW_ALIGNMENT")
need("data-demo-toast" not in HTML and "data-demo-toast" not in JS, "PROD_DEMO_ACTIONS_ABSENT")
need("Expirado · gere um novo código" in JS, "PAIRING_EXPIRY_UI")
need("Confirmar revogação" in JS and "data-confirm-revoke" not in HTML and "window.confirm" not in JS, "DEVICE_REVOKE_CONFIRMATION")
need(WORKER.count("error_code = 'DEVICE_REVOKED'") >= 2, "PORTAL_DEVICE_REVOKE_CANCELS_CALLS")
need("function requirePortalMutationOrigin" in WORKER and 'if (!origin || origin !== expectedOrigin)' in WORKER and WORKER.count("requirePortalMutationOrigin(request);") >= 4, "PORTAL_MUTATION_ORIGIN_GUARD")
need("fonts.googleapis.com" not in HTML and "fonts.gstatic.com" not in HTML, "EXTERNAL_FONT_DEPENDENCY_ABSENT")
need("'TRIAL', 'Trial', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 100, 'ACTIVE'" in TRIAL_MIGRATION, "TRIAL_PLAN_HISTORICAL_BASE")
need("'TRIAL', 'Free', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 10000, 'ACTIVE'" in COMMERCIAL_MIGRATION, "FREE_PLAN_CANONICAL_LIMIT")
need("'STANDARD', 'Pro', 'HARA_COMMANDER_GOVERNED_INVOKE', 'NONE', NULL, 'ACTIVE'" in COMMERCIAL_MIGRATION, "PRO_PLAN_CANONICAL_UNLIMITED")
need('10.000 <small>chamadas / mês</small>' in HTML and '10.000 chamadas renovadas todo mês' in HTML, "FREE_PLAN_UI_ALIGNMENT")
need('R$ 80 <small>/ mês</small>' in HTML and 'Chamadas ilimitadas' in HTML, "PRO_PLAN_UI_ALIGNMENT")
need('100 <small>execuções / mês</small>' not in HTML, "STALE_TRIAL_QUOTA_ABSENT")
need(
    'activeDevices.find((device) => Boolean(device.selected))' not in JS
    and 'device-selected-badge' not in JS
    and 'data-select-device' not in JS
    and 'select.textContent = device.selected' not in JS
    and 'setState("Offline", "Nenhum computador online")' in JS
    and '" computadores online"' in JS,
    "DEVICE_FLEET_STATE_UX",
)
need(
    'COMPUTER_REQUIRED' in DEVICE_TARGETING
    and 'resolveCustomerTargetDevice' in WORKER
    and 'computer: z.string().min(1).max(120).optional()' in CUSTOMER_MCP
    and 'JOIN commander_device_selections s' not in WORKER[WORKER.index('async function enqueueDeviceCall'):WORKER.index('async function deviceCallStatus')],
    "DEVICE_EXPLICIT_TARGET_ROUTING",
)
need(
    'data-device-section-tab="devices"' in HTML
    and 'data-device-section-tab="connect"' in HTML
    and 'data-device-section-panel="devices"' in HTML
    and 'data-device-section-panel="connect"' in HTML
    and 'function setDeviceSectionTab(next)' in JS
    and 'setDeviceSectionTab("devices")' in JS
    and ".devices-section-tabs" in CSS
    and ".devices-panel-compact" in CSS,
    "DEVICE_WORKSPACE_INFORMATION_ARCHITECTURE",
)
need(
    '<span class="eyebrow"><i></i> USO</span>' not in HTML
    and '<span class="eyebrow"><i></i> PLANO</span>' not in HTML
    and '<span class="eyebrow"><i></i> INTEGRAÇÕES</span>' not in HTML
    and '<span class="eyebrow"><i></i> SEGURANÇA</span>' not in HTML
    and '<h1 id="plans-title">Plano e cobrança</h1>' in HTML
    and '<h1 id="usage-title">Uso</h1>' in HTML
    and '<h1 id="security-title">Configurações</h1>' in HTML,
    "WORKSPACE_SINGLE_TITLE_HIERARCHY",
)
sidebar_block = HTML.split('<template id="sidebarTemplate">',1)[1].split('</template>',1)[0]
need(
    sidebar_block.count('data-app-go=') == 4
    and 'data-app-go="devices"' in sidebar_block
    and 'data-app-go="usage"' in sidebar_block
    and 'data-app-go="plans"' in sidebar_block
    and 'data-app-go="security"' in sidebar_block
    and 'data-app-go="dashboard"' not in sidebar_block
    and 'data-app-go="connections"' not in sidebar_block
    and '<span>Computadores</span>' in sidebar_block
    and '<span>Uso</span>' in sidebar_block
    and '<span>Plano e cobrança</span>' in sidebar_block
    and '<span>Configurações</span>' in sidebar_block,
    "CUSTOMER_NAV_SIMPLE_FOUR_ITEMS",
)
need(
    'encodeURIComponent("/#devices")' in JS
    and 'route("devices");' in JS
    and 'id="devices-title"' in HTML
    and 'id="usage-title"' in HTML
    and 'O Commander na nuvem mantém apenas o mínimo necessário' in HTML,
    "CUSTOMER_DEFAULT_DEVICES_ROUTE",
)
need(
    'device-where-panel' in HTML
    and '<b>ChatGPT</b>' in HTML
    and '<b>Claude</b>' in HTML
    and '<b>Qualquer cliente MCP</b>' in HTML
    and 'data-copy-simple-mcp' in HTML,
    "DEVICE_WHERE_TO_USE_SURFACE",
)
need(
    "UX polish: single page title, larger useful content, restrained glow" in CSS
    and "font-size:24px" in CSS
    and "box-shadow:0 2px 7px rgba(218,156,19,.07)" in CSS,
    "WORKSPACE_TYPOGRAPHY_AND_LOW_GLOW",
)
need(
    "UX Wave 3 — compact computers workspace and readable navigation" in CSS
    and "font-size:14px" in CSS
    and ".top-session-copy b" in CSS
    and ".devices-workspace-head" in CSS,
    "DEVICE_WORKSPACE_DENSITY_AND_NAV_LEGIBILITY",
)
need(
    HTML.count("data-create-pairing") == 1
    and 'data-os-choice="linux"' in HTML
    and 'data-os-choice="windows"' in HTML
    and 'data-os-panel="linux"' in HTML
    and 'data-os-panel="windows"' in HTML
    and "Sempre permitir" in HTML
    and "Pedir confirmação" in HTML
    and "<b>Pronto</b>" in HTML
    and "hara-commander doctor" in HTML
    and "Mantenha o console aberto enquanto usar a IA" not in HTML
    and 'tabindex="-1" aria-live="polite"' in HTML
    and 'function setInstallOs(os)' in JS,
    "PAIRING_ONBOARDING_ORDER",
)
onboarding_block = HTML.split('<div class="device-onboarding">',1)[1].split('</section>',1)[0]
need(
    onboarding_block.count('class="onboarding-step-no"') == 3
    and '<span class="onboarding-step-no">01</span>' in onboarding_block
    and '<span class="onboarding-step-no">02</span>' in onboarding_block
    and '<span class="onboarding-step-no">03</span>' in onboarding_block
    and '<span class="onboarding-step-no">04</span>' not in onboarding_block
    and '<span class="onboarding-step-no">05</span>' not in onboarding_block
    and "Instale e pronto" in onboarding_block
    and "Sempre permitir" in onboarding_block
    and "mantenha esse console aberto" not in onboarding_block
    and "sessão de IA precisa ser aberta manualmente" not in onboarding_block,
    "COMMERCIAL_ONBOARDING_THREE_STEPS",
)
need(
    'id="dashboardUsageProgress"' in HTML
    and 'id="dashboardPlanDetail"' in HTML
    and 'planCard.classList.toggle("trial", isTrial)' in JS
    and 'dashboardProgress.setAttribute("aria-valuenow"' in JS,
    "DASHBOARD_STATUS_SUMMARY",
)
need(
    'id="internalBetaDiagnostics"' not in HTML
    and 'DIAGNÓSTICO LOCAL · BETA' not in HTML
    and 'id="activityTotal"' not in HTML
    and 'id="activitySuccessRate"' not in HTML
    and 'id="activityAvgLatency"' not in HTML
    and 'id="activityTransport"' not in HTML
    and 'id="sloSummaryCard"' not in HTML
    and 'id="activityTopTools"' not in HTML
    and 'id="activityTopErrors"' not in HTML
    and 'id="usageLedger"' not in HTML
    and 'data-slo-ack' not in HTML
    and 'data-slo-escalate' not in HTML
    and 'if (next === "usage") loadUsageActivity();' not in JS
    and 'O Commander na nuvem mantém apenas o mínimo necessário' in HTML,
    "USAGE_PRODUCT_BOUNDARY_NO_INTERNAL_DIAGNOSTICS",
)
need(
    'id="usageCardTransactions"' in HTML
    and 'id="usageCardCapacity"' in HTML
    and 'id="usageCardPlan"' in HTML
    and 'id="usageCardPeriod"' in HTML
    and 'setText("usageCardTransactions"' in JS
    and 'setText("usageCardCapacity"' in JS
    and 'setText("usageCardPlan"' in JS
    and 'setText("usageCardPeriod"' in JS,
    "USAGE_CUSTOMER_SUMMARY_CARDS",
)
bootstrap_block = WORKER.split('url.pathname === "/api/portal/bootstrap"',1)[1].split('url.pathname === "/api/portal/dashboard"',1)[0]
need(
    'transaction_history: payload.transaction_history' in bootstrap_block,
    "USAGE_BOOTSTRAP_TRANSACTION_HISTORY_PARITY",
)
need(
    '.usage-product-grid{grid-template-columns:1.05fr 1.05fr 1.4fr 1fr;gap:18px;margin-top:24px' in CSS
    and '.usage-product-grid .summary-card{min-height:144px' in CSS,
    "USAGE_CUSTOMER_CARD_SPACING",
)
history_block = WORKER.split("async function productTransactionHistory",1)[1].split("async function dashboardForSubject",1)[0]
need(
    'COUNT(*) AS calls_total' in history_block
    and 'AS calls_7d' in history_block
    and 'WHERE tenant_id = ? AND subject_id = ?' in history_block
    and 'detail_level: "AGGREGATE_ONLY"' in history_block
    and 'tool_id' not in history_block
    and 'payload_json' not in history_block
    and 'result_json' not in history_block,
    "USAGE_TRANSACTION_HISTORY_AGGREGATE_ONLY",
)
need(
    'url.pathname === "/api/portal/activity"' in WORKER
    and 'url.pathname === "/api/portal/slo"' in WORKER
    and 'INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT' in WORKER,
    "PUBLIC_DIAGNOSTIC_ROUTES_FAIL_CLOSED",
)
need(
    'if (toolId === "hara.activity" || toolId === "hara.calls.recent")' in WORKER
    and 'LOCAL_DIAGNOSTICS_REQUIRE_SIGNED_AGENT_UPDATE' in WORKER,
    "MCP_REMOTE_HISTORY_FAIL_CLOSED",
)
need(
    'CUSTOMER_MCP_SIMPLE_TOOLS' in SIMPLE_MCP
    and '"read_file"' in SIMPLE_MCP
    and '"write_file"' in SIMPLE_MCP
    and '"start_process"' in SIMPLE_MCP
    and '"read_process_output"' in SIMPLE_MCP
    and 'args.interactive ? "hara.process.start" : "hara.process.run"' in SIMPLE_MCP
    and 'handleSimpleCustomerMcpRequest' in WORKER
    and 'profile === "simple"' in WORKER
    and 'MCP_PROFILE_INVALID' in WORKER,
    "MCP_SIMPLE_PROFILE",
)
need(
    'class="skip-link" href="#mainContent"' in HTML
    and '<main id="mainContent" tabindex="-1">' in HTML
    and ":focus-visible" in CSS
    and 'aria-label="Sistema operacional"' in HTML
    and '["ArrowLeft", "ArrowRight"]' in JS,
    "ACCESSIBILITY_NAVIGATION",
)
need(
    'class="connection-readiness"' in HTML
    and HTML.count('integration-badge') >= 2
    and 'data-copy-local-mcp' in HTML
    and 'data-copy-simple-mcp' in HTML
    and "MCP Local" in HTML
    and "MCP Remoto" in HTML
    and "0 relay por operação" in HTML
    and "24 comandos simples" in HTML
    and "/api/mcp?profile=simple" in HTML
    and 'copyText("hara-commander mcp"' in JS
    and 'window.location.origin + "/api/mcp?profile=simple"' in JS
    and "Ainda não disponível" not in HTML
    and "Aguardando homologação do primeiro dispositivo real" not in HTML,
    "CONNECTIONS_HONEST_READINESS",
)
need(
    ".workspace-mode .sidebar{position:fixed" in CSS
    and 'data-app-go="devices"' in sidebar_block
    and 'data-app-go="usage"' in sidebar_block
    and 'data-app-go="plans"' in sidebar_block
    and 'data-app-go="security"' in sidebar_block
    and 'data-mobile-more' not in sidebar_block
    and 'desktop-secondary' not in sidebar_block,
    "MOBILE_NAVIGATION",
)
need(
    "function deviceApprovalLabel(mode)" in JS
    and '"PERSISTENT_TRUSTED"' in JS
    and '"Sempre permitido"' in JS
    and '"SESSION_TRUSTED"' in JS
    and '"Por sessão"' in JS
    and '"ASK_EVERY_ACTION"' in JS
    and '"Confirmação"' in JS
    and ".device-policy.persistent" in CSS,
    "DEVICE_APPROVAL_POLICY_VISIBILITY",
)
need(
    "function deviceReadiness(device)" in JS
    and '"PERSISTENT_TRUSTED"' in JS
    and '"SESSION_TRUSTED"' in JS
    and 'label:"Pronto"' in JS
    and 'label:"Atenção"' in JS
    and "function deviceDiagnosticCommand(platform)" in JS
    and "hara-commander doctor && hara-commander support" in JS
    and "data-copy-device-diagnostic" in JS
    and "Comando de diagnóstico copiado." in JS,
    "DEVICE_SELF_SERVICE_SUPPORT",
)
need(
    'class="panel quickstart-panel"' in HTML
    and 'id="quickStartDeviceState"' in HTML
    and 'data-copy-first-prompt' in HTML
    and 'Verifique se meu computador está online e mostre as informações básicas dele.' in JS
    and 'quickStartDeviceStep' in JS
    and 'onlineCount > 0' in JS,
    "DEVICE_FIRST_SUCCESS_QUICKSTART",
)
need(
    'id="serviceHealthPill"' in HTML
    and 'id="serviceHealthDetail"' in HTML
    and 'data-refresh-service-health' in HTML
    and "async function loadServiceHealth(trigger=null)" in JS
    and 'fetch("/api/health"' in JS
    and 'payload?.service === "hara-commander"' in JS
    and '"Operacional"' in JS
    and '"Degradado"' in JS
    and 'next === "security"' in JS,
    "CUSTOMER_SERVICE_HEALTH_SURFACE",
)
need(
    'data-beta-access' in HTML
    and 'Solicitar acesso beta' in HTML
    and 'activation.first_checkout_ready || standardCurrent' in JS
    and 'Standard está disponível em beta por convite.' in JS
    and 'betaAccess.hidden' in JS,
    "BETA_INVITE_FALLBACK",
)
need(
    "function renderDeviceLoading()" in JS
    and 'list.setAttribute("aria-busy", "true")' in JS
    and "device-skeleton" in CSS
    and "body.product-loading .summary-card::after" in CSS,
    "LOADING_EMPTY_STATES",
)
need('payload?.code === "ENTITLEMENT_NOT_FOUND"' in JS and "Plano não disponível" in JS, "ENTITLEMENT_ERROR_SEMANTICS")
need(JS.index("await hydrateSessionHeader()") < JS.index("route(initialRoute, false)"), "AUTH_BOOTSTRAP_ORDER")
need(".system-banner.show{display:flex}" in CSS and ".workspace-mode .system-banner.show" not in CSS, "AUTH_BANNER_GLOBAL_VISIBILITY")
need(
    'class="topnav"' not in HTML
    and HTML.count('class="theme-toggle"') == 1
    and "theme-icon-moon" in HTML
    and "theme-icon-sun" in HTML
    and '<a class="brand" href="https://www.haralabs.com.br/"' in HTML
    and '<div class="workspace">' not in HTML
    and "sidebar-bottom" not in HTML
    and 'class="side-nav side-nav-simple"' in HTML
    and HTML.count('class="nav-icon"') >= 4
    and "<span>▦</span>" not in HTML
    and "<span>▣</span>" not in HTML,
    "APPROVED_NAV_LAYOUT",
)
need(
    ".side-nav button:hover,.side-nav-link:hover" in CSS
    and "transform:translateX(3px)" in CSS
    and ".side-nav button.active::before" in CSS,
    "APPROVED_NAV_INTERACTION",
)
need(
    "brandLink" not in JS
    and 'const themeBtn = document.querySelector(".theme-toggle");' in JS
    and 'localStorage.setItem("hara-theme", next)' in JS
    and 'html[data-theme="dark"] .theme-icon-sun{display:block}' in CSS,
    "APPROVED_HEADER_BEHAVIOR",
)
need('OWNER: "Proprietário"' in JS and 'data-user-role>Owner<' not in HTML and 'usage: "Uso · H.A.R.A. Commander"' in JS, "PORTUGUESE_ROLE_AND_TITLE_UX")
need("https://www.haralabs.com.br/legal/termos/" in HTML and "https://www.haralabs.com.br/legal/privacidade/" in HTML and 'class="auth-legal"' in HTML and 'class="product-legal-links"' in HTML, "LEGAL_LINKS_READY")
need("#dashboardInvokes" not in CSS and ".activity-list" not in CSS, "DEAD_ACTIVITY_CSS_ABSENT")
need('class="user-chip"' not in HTML, "DUPLICATE_INTERNAL_SESSION_IDENTITY_ABSENT")
need(".user-chip" not in CSS, "DEAD_USER_CHIP_CSS_ABSENT")
need(
    '<span class="plan-label">FREE</span>' in HTML
    and '<span class="plan-label">PRO</span>' in HTML
    and '<span class="plan-label">SCALE</span>' not in HTML
    and 'data-billing-plan="SCALE"' not in HTML
    and 'grid-template-columns:repeat(2,minmax(0,1fr))' in CSS,
    "COMMERCIAL_TWO_PLAN_SURFACE",
)
need(
    'id="billingReadiness"' in HTML
    and 'data-billing-ready="provider"' in HTML
    and 'data-billing-ready="catalog"' in HTML
    and 'data-billing-ready="price"' in HTML
    and 'data-billing-ready="checkout"' in HTML
    and 'activation.standard_checkout_ready' in JS
    and 'activation.standard_catalog_active' in JS
    and 'activation.standard_price_configured' in JS,
    "BILLING_READINESS_UX",
)

prod = "https://commander.haralabs.com.br"
dev = "hara-commander-dev-v2.tiago-sartori.workers.dev"
for label, content in (("HTML", HTML), ("JS", JS), ("LINUX", LINUX), ("WINDOWS", WINDOWS)):
    need(prod in content, f"{label}_PROD_DOMAIN")
    need(dev not in content, f"{label}_DEV_URL_LEAK")

need("border-top:2px solid rgba(233,177,40,.92)" in CSS, "LIGHT_TOP_GOLD")
need("border-bottom:2px solid rgba(233,177,40,.82)" in CSS, "LIGHT_BOTTOM_GOLD")
need('html[data-theme="dark"] .topbar' in CSS, "DARK_TOPBAR")
need("border-top:2px solid rgba(72,109,134,.56)" in CSS, "DARK_TOP_BLUE")
need("border-bottom:2px solid rgba(27,64,84,.96)" in CSS, "DARK_BOTTOM_BLUE")
need(not (ROOT / "public/dev/commander").exists(), "DEV_SNAPSHOT_ARCHIVE")
need(not (APP / "seed/dev.sql").exists(), "DEV_SEED_RESIDUE")
need("Strict-Transport-Security: max-age=31536000; includeSubDomains" in HEADERS, "STATIC_HSTS")
need("Content-Security-Policy:" in HEADERS and "frame-ancestors 'none'" in HEADERS, "STATIC_CSP")
need("connect-src 'self' http://127.0.0.1:32145" in HEADERS, "LOCALHOST_ACTIVITY_CSP")
need("http://0.0.0.0" not in HEADERS and "192.168." not in HEADERS and "10.0.0.0" not in HEADERS, "LOCALHOST_ACTIVITY_CSP_NARROW")
need("upgrade-insecure-requests" not in HEADERS, "LOCALHOST_ACTIVITY_NOT_UPGRADED")
need("X-Content-Type-Options: nosniff" in HEADERS, "STATIC_NOSNIFF")
need("SECURITY_HEADERS" in WORKER and '"strict-transport-security"' in WORKER, "WORKER_SECURITY_HEADERS")
need("7403" in READBACK and "TRANSIENT_MARKERS" in READBACK, "D1_TRANSIENT_RETRY")
need("function sanitizeErrorCode" in WORKER and "INVALID_JSON: 400" in WORKER, "ERROR_SANITIZATION")
need('authorize.searchParams.set("prompt", "select_account")' in AUTH and 'authorize.searchParams.set("max_age", "0")' in AUTH, "OIDC_ACCOUNT_SWITCH")
need("cleanupExpiredOidcTransactions" in AUTH and "TX_RETENTION_BATCH = 100" in AUTH and ".run().catch(() => null)" in AUTH, "OIDC_TX_RETENTION")
need("DELETE FROM oidc_transactions WHERE expires_at_utc <= ?" not in AUTH, "OIDC_TX_UNBOUNDED_DELETE_ABSENT")
need("julianday(expires_at_utc) > julianday('now')" in READBACK, "D1_ACTIVE_SESSION_TIME_SEMANTICS")

print("COMMANDER_PROD_CONFIG=PASS")
print("COMMANDER_PROD_D1_ISOLATION=PASS")
print("COMMANDER_PROD_DEV_ENDPOINT_GATE=PASS")
print("COMMANDER_PROD_DOMAIN_REFERENCES=PASS")
print("COMMANDER_PROD_AUTH_FIRST_PAINT=PASS")
print("COMMANDER_PROD_API_OVERRIDE=LOCAL_ONLY")
print("COMMANDER_PROD_SCENARIO_OVERRIDE=LOCAL_ONLY")
print("COMMANDER_PROD_PROTECTED_ROUTE_GUARD=PASS")
print("COMMANDER_PROD_AUTH_ERROR_VIEW_ALIGNMENT=PASS")
print("COMMANDER_PROD_DEMO_ACTIONS=ABSENT")
print("COMMANDER_PROD_PAIRING_EXPIRY_UX=PASS")
print("COMMANDER_PROD_DEVICE_REVOKE_CONFIRMATION=PASS")
print("COMMANDER_PROD_PORTAL_REVOKE_CANCELS_CALLS=PASS")
print("COMMANDER_PROD_PORTAL_MUTATION_ORIGIN_GUARD=PASS")
print("COMMANDER_PROD_EXTERNAL_FONT_DEPENDENCY=ABSENT")
print("COMMANDER_PROD_TRIAL_PLAN_UI_ALIGNMENT=PASS")
print("COMMANDER_PROD_FALSE_QUOTA_CLAIMS=ABSENT")
print("COMMANDER_PROD_DEVICE_FLEET_STATE_UX=PASS")
print("COMMANDER_PROD_DEVICE_EXPLICIT_TARGET_ROUTING=PASS")
print("COMMANDER_PROD_PAIRING_ONBOARDING_ORDER=PASS")
print("COMMANDER_PROD_DASHBOARD_STATUS_SUMMARY=PASS")
print("COMMANDER_PROD_USAGE_DETAIL_HONEST_STATE=PASS")
print("COMMANDER_PROD_ACCESSIBILITY_NAVIGATION=PASS")
print("COMMANDER_PROD_CONNECTIONS_HONEST_READINESS=PASS")
print("COMMANDER_PROD_MOBILE_NAVIGATION=PASS")
print("COMMANDER_PROD_LOADING_EMPTY_STATES=PASS")
print("COMMANDER_PROD_ENTITLEMENT_ERROR_SEMANTICS=PASS")
print("COMMANDER_PROD_AUTH_BOOTSTRAP_ORDER=PASS")
print("COMMANDER_PROD_AUTH_BANNER_GLOBAL_VISIBILITY=PASS")
print("COMMANDER_PROD_APPROVED_NAV_LAYOUT=PASS")
print("COMMANDER_PROD_APPROVED_NAV_INTERACTION=PASS")
print("COMMANDER_PROD_APPROVED_HEADER_BEHAVIOR=PASS")
print("COMMANDER_PROD_PORTUGUESE_ROLE_AND_TITLE_UX=PASS")
print("COMMANDER_PROD_LEGAL_LINKS=PASS")
print("COMMANDER_PROD_DEAD_ACTIVITY_CSS=ABSENT")
print("COMMANDER_PROD_LIGHT_HEADER_SIGNATURE=PASS")
print("COMMANDER_PROD_DARK_HEADER_SIGNATURE=PASS")
print("COMMANDER_PROD_DEV_SNAPSHOT_ARCHIVE=ABSENT")
print("COMMANDER_PROD_DEV_SEED=ABSENT")
print("COMMANDER_PROD_STATIC_SECURITY_HEADERS=PASS")
print("COMMANDER_PROD_WORKER_SECURITY_HEADERS=PASS")
print("COMMANDER_PROD_D1_TRANSIENT_RETRY=READY")
print("COMMANDER_PROD_ERROR_SANITIZATION=PASS")
print("COMMANDER_PROD_OIDC_ACCOUNT_SWITCH=PASS")
print("COMMANDER_PROD_OIDC_TX_RETENTION=READY")
print("COMMANDER_PROD_SESSION_TIME_SEMANTICS=PASS")
