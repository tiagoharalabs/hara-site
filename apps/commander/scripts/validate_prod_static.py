#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CFG = json.loads((APP / "wrangler.jsonc").read_text())
WORKER = (APP / "src/worker.js").read_text()
AUTH = (APP / "src/auth.js").read_text()
HTML = (APP / "public/index.html").read_text()
JS = (APP / "public/app.js").read_text()
CSS = (APP / "public/styles.css").read_text()
LINUX = (APP / "public/install/linux.sh").read_text()
WINDOWS = (APP / "public/install/windows.ps1").read_text()
HEADERS = (APP / "public/_headers").read_text()
READBACK = (APP / "scripts/commander_prod_readback.py").read_text()
TRIAL_MIGRATION = (APP / "migrations/0008_trial_onboarding.sql").read_text()

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
need("styles.css?v=20260925-neon1" in HTML, "STYLE_CACHE_KEY")
need("app.js?v=20260925-neon1" in HTML, "SCRIPT_CACHE_KEY")
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
need("'TRIAL', 'Trial', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 100, 'ACTIVE'" in TRIAL_MIGRATION, "TRIAL_PLAN_CANONICAL_LIMIT")
need('100 <small>execuções / mês</small>' in HTML and '1.000 <small>invokes / período</small>' not in HTML and '10.000 <small>invokes / período</small>' not in HTML, "TRIAL_PLAN_UI_ALIGNMENT")
need("10000" not in HTML and "10000" not in JS and "10.000" not in HTML and "1.000" not in HTML, "FALSE_QUOTA_CLAIMS_ABSENT")
need(
    'activeDevices.find((device) => Boolean(device.selected))' in JS
    and 'setState("Offline"' in JS
    and 'setState("Pronto"' in JS
    and "device-selected-badge" in JS
    and 'row.classList.add("selected")' in JS,
    "DEVICE_SELECTION_STATE_UX",
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
    and '<h1 id="plans-title">Plano</h1>' in HTML
    and '<h1 id="usage-title">Uso e limites</h1>' in HTML,
    "WORKSPACE_SINGLE_TITLE_HIERARCHY",
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
    and "Aguarde o dispositivo aparecer em Dispositivos" in HTML
    and 'tabindex="-1" aria-live="polite"' in HTML
    and 'function setInstallOs(os)' in JS,
    "PAIRING_ONBOARDING_ORDER",
)
need(
    'id="dashboardUsageProgress"' in HTML
    and 'id="dashboardPlanDetail"' in HTML
    and 'planCard.classList.toggle("trial", isTrial)' in JS
    and 'dashboardProgress.setAttribute("aria-valuenow"' in JS,
    "DASHBOARD_STATUS_SUMMARY",
)
need("Detalhamento em homologação" in HTML and "renderActivity(" not in JS and "activityList" not in JS, "USAGE_DETAIL_HONEST_STATE")
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
    and HTML.count('class="integration-badge"') >= 2
    and "Cinco ferramentas governadas" in HTML
    and "Ainda não disponível" in HTML
    and "Aguardando homologação do primeiro dispositivo real" in HTML,
    "CONNECTIONS_HONEST_READINESS",
)
need(
    'data-mobile-more' in HTML
    and 'data-mobile-more-menu' in HTML
    and "function toggleMobileMore(button)" in JS
    and "closeMobileMoreMenus()" in JS
    and ".workspace-mode .sidebar{position:fixed" in CSS
    and ".side-nav>.mobile-more-toggle,.mobile-more-menu{display:none!important}" in CSS
    and ".workspace-mode .side-nav>[data-app-go]:not(.desktop-secondary),.workspace-mode .side-nav>.mobile-more-toggle{display:flex!important" in CSS
    and ".workspace-mode .side-nav>.desktop-secondary{display:none!important}" in CSS
    and ".mobile-more-menu:not([hidden]){display:flex}" in CSS,
    "MOBILE_NAVIGATION",
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
    and "side-nav-link" in HTML
    and 'href="https://www.haralabs.com.br/support/"' in HTML
    and HTML.count('class="nav-icon"') >= 7
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
need('OWNER: "Proprietário"' in JS and 'data-user-role>Owner<' not in HTML and 'usage: "Uso & limite · H.A.R.A. Commander"' in JS, "PORTUGUESE_ROLE_AND_TITLE_UX")
need("https://www.haralabs.com.br/legal/termos/" in HTML and "https://www.haralabs.com.br/legal/privacidade/" in HTML and 'class="auth-legal"' in HTML and 'class="product-legal-links"' in HTML, "LEGAL_LINKS_READY")
need("#dashboardInvokes" not in CSS and ".activity-list" not in CSS, "DEAD_ACTIVITY_CSS_ABSENT")
need('class="user-chip"' not in HTML, "DUPLICATE_INTERNAL_SESSION_IDENTITY_ABSENT")
need(".user-chip" not in CSS, "DEAD_USER_CHIP_CSS_ABSENT")

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
print("COMMANDER_PROD_DEVICE_SELECTION_STATE_UX=PASS")
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
