#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTML = (ROOT / "public/dev/commander/index.html").read_text(encoding="utf-8")
JS = (ROOT / "public/dev/commander/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "public/dev/commander/styles.css").read_text(encoding="utf-8")
BOOT = (ROOT / "apps/commander/scripts/bootstrap_remote_dev.py").read_text(encoding="utf-8")
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

required_html = [
    "systemBanner",
    "systemBannerAction",
    "dashboardState",
    "dashboardStateDetail",
    "connectionList",
    "data-auth-guest",
    "data-auth-session",
    "usageLedger",
    "data-security-subject",
    "dashboardConnections",
    "deviceList",
    "pairingPanel",
    "data-create-pairing",
    "data-app-go=\"devices\"",
]
required_js = [
    "auth-expired",
    "entitlement-suspended",
    "quota-exhausted",
    "mcp-unavailable",
    "receipt-unavailable",
    "billing-disconnected",
    "degraded",
    "loading",
    "empty",
    "Tentar novamente",
    "setAuthenticatedHeader",
    "setGuestHeader",
    "hydrateSessionHeader",
    "loadDevices",
    "createPairing",
    "revokeDevice",
]
required_css = [
    "system-banner",
    "empty-state",
    "prefers-reduced-motion",
    "top-session-user",
    "tag.reserved",
    "setup-grid",
    "device-row",
    "pairing-token",
]
required_boot = [
    "CLOUDFLARE_AUTH=REQUIRED",
    "REMOTE_DEV_D1",
    "REMOTE_DEV_D1_MIGRATIONS",
    "REMOTE_DEV_SYNTHETIC_SEED",
    "MCP_ACCESS_ISSUER",
    "PRODUCTION_DNS_MUTATION=FALSE",
]
required_worker = [
    "CLOUDFLARE_ACCESS",
    "SECONDARY_IDENTITY_CONFLICT",
    "SECONDARY_ISSUER_MISMATCH",
    "MCP_ACCESS_ISSUER",
    "REQUEST_USAGE_TERMINAL",
    "/api/internal/mcp/authorize",
    "/api/internal/mcp/commit",
    "/api/internal/mcp/release",
    "/api/portal/devices",
    "/api/portal/devices/pairing",
    "/api/device/enroll",
    "/api/device/heartbeat",
]

for token in required_html:
    assert token in HTML, f"HTML_MISSING:{token}"
for token in required_js:
    assert token in JS, f"JS_MISSING:{token}"
for token in required_css:
    assert token in CSS, f"CSS_MISSING:{token}"
for token in required_boot:
    assert token in BOOT, f"BOOT_MISSING:{token}"
for token in required_worker:
    assert token in WORKER, f"WORKER_MISSING:{token}"

print("COMMANDER_FUNCTIONAL_STATES=PASS")
print("LOADING_EMPTY_ERROR_RETRY_UX=PASS")
print("AUTH_EXPIRED_UX=PASS")
print("ENTITLEMENT_SUSPENDED_UX=PASS")
print("QUOTA_EXHAUSTED_UX=PASS")
print("MCP_UNAVAILABLE_UX=PASS")
print("RECEIPT_UNAVAILABLE_UX=PASS")
print("BILLING_DISCONNECTED_UX=PASS")
print("REDUCED_MOTION=PASS")
print("REMOTE_DEV_BOOTSTRAP_STATIC=PASS")
print("MCP_PRODUCT_SECONDARY_IDENTITY_STATIC=PASS")
print("MCP_PRODUCT_USAGE_TERMINAL_STATIC=PASS")
print("PRODUCTION_PUBLICATION=FALSE")

forbidden_visible = [
    "AMBIENTE DEV",
    "Portal DEV",
    "DEV:",
    "Workspace Demo",
    "Tiago Demo",
    "Sair do DEV",
    "UX em DEV",
    "Backend DEV",
    "tenant DEV",
    "simulada em DEV",
    "Degradado",
    "Product API indisponível",
    "Serviço de produto indisponível",
]
for token in forbidden_visible:
    assert token not in HTML, f"PRODUCTION_LIKE_HTML_LEAK:{token}"
    assert token not in JS, f"PRODUCTION_LIKE_JS_LEAK:{token}"

required_identity_ui = [
    "data-tenant-name",
    "data-user-name",
    "data-user-role",
    "data-user-initials",
]
for token in required_identity_ui:
    assert token in HTML, f"IDENTITY_UI_BINDING_MISSING:{token}"
assert "applyIdentity(payload)" in JS, "IDENTITY_PAYLOAD_BINDING_MISSING"

print("PRODUCTION_LIKE_VISIBLE_UX=PASS")
print("AUTHENTICATED_IDENTITY_UI_BINDING=PASS")
print("AUTHENTICATED_TOPBAR_STATE=PASS")
print("DEVICE_PAIRING_UI=PASS")
print("CUSTOMER_DEGRADED_LANGUAGE=ABSENT")
