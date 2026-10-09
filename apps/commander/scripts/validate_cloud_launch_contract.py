#!/usr/bin/env python3
"""Static acceptance for Cloud-first commercial MCP distribution; not E2E approval."""
from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
PUBLIC = APP / "public"
PLUGIN = APP / "plugin-submission"
SOURCE = (PUBLIC / "install/linux.sh").read_text()
PORTAL = (PUBLIC / "index.html").read_text()
APP_JS = (PUBLIC / "app.js").read_text()
WORKER = (APP / "src/worker.js").read_text()
MCP = (APP / "src/customer-mcp-simple.mjs").read_text()
MANIFEST = json.loads((PUBLIC / "release/agent-manifest.json").read_text())
PACKAGE = json.loads((PLUGIN / "plugin.json").read_text())
MCP_CONFIG = json.loads((PLUGIN / "mcp.json").read_text())


def check(ok: bool, label: str) -> None:
    if not ok:
        raise AssertionError("CLOUD_LAUNCH_" + label)
    print("COMMANDER_CLOUD_LAUNCH_" + label + "=PASS")


check('  TRANSPORT_MODE="OUTBOUND_RELAY"\nfi\n\nTUNNEL_AUTOSTART=' in SOURCE,
      "FIRST_INSTALL_CLOUD_DEFAULT")
check('LOCAL_TUNNEL|TUNNEL|LOCAL) TRANSPORT_MODE="LOCAL_TUNNEL"' in SOURCE,
      "DIRECT_ONLY_EXPLICIT_OPT_IN")
check('OPENAI_TUNNEL_AUTOSTART_REQUIRES_DIRECT_TRANSPORT' in SOURCE,
      "NO_OPENAI_TUNNEL_ON_CLOUD")
check('let installTransportMode = "OUTBOUND_RELAY"' in APP_JS and
      '" HARA_COMMANDER_TRANSPORT_MODE=" + installTransportMode' in APP_JS,
      "PORTAL_TRANSPORT_SELECTED_IN_INSTALLER")
check('data-transport-choice="cloud"' in PORTAL and
      'data-transport-choice="direct"' in PORTAL and
      'Cloud (padrão)' in PORTAL, "CLOUD_PUBLIC_UI_DEFAULT")
check("o conteúdo transita pelo Gateway" in PORTAL and
      "HARA Identity" in PORTAL and "OAuth" in PORTAL,
      "USER_TRANSPORT_DISCLOSURE")
check('customer_services_relay: false' in WORKER and
      'url.pathname === "/api/mcp"' in WORKER and
      'allowedHosts: ["commander.haralabs.com.br"]' in WORKER,
      "INDEPENDENT_CUSTOMER_MCP_EDGE")
check('const DEVICE_CALL_TTL_SECONDS = 50;' in WORKER and
      'async function redactExpiredDeviceCallContent' in WORKER and
      "payload_json TEXT NOT NULL" in (APP / "migrations/0012_outbound_relay_offline.sql").read_text(),
      "TRANSIENT_D1_CONTENT_DISCLOSED")
check('createSimpleCustomerMcpServer' in MCP or 'registerTool' in MCP,
      "SIMPLE_PRODUCT_MCP_SURFACE")

interface = PACKAGE["extensions"]["com.openai"]["interface"]
review = PACKAGE["extensions"]["com.openai"]["review"]
endpoint = MCP_CONFIG["mcpServers"]["hara-commander"]["url"]
check(endpoint == "https://commander.haralabs.com.br/api/mcp?profile=simple",
      "PLUGIN_ONLY_COMMERCIAL_ENDPOINT")
check(interface["displayName"] == "H.A.R.A. Commander" and
      interface["developerName"] == "H.A.R.A. Labs" and
      len(interface["shortDescription"]) <= 30 and
      len(interface["displayName"]) <= 30,
      "PLUGIN_BRAND_AND_LISTING")
check(all(interface[key].startswith("https://") for key in
          ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL")),
      "PLUGIN_LEGAL_URLS")
check(len(review["test_cases"]["positive"]) == 5 and
      len(review["test_cases"]["negative"]) == 3,
      "PLUGIN_5_POSITIVE_3_NEGATIVE_DRAFT_CASES")
check(all(case["tools_triggered"] in MCP for case in review["test_cases"]["positive"]),
      "PLUGIN_TEST_TOOL_NAMES_PRESENT")

for name, expected in (("logo.png",512),("icon.png",256)):
    data=(PLUGIN / "assets" / name).read_bytes()
    check(data[:8] == bytes.fromhex("89504e470d0a1a0a") and
          struct.unpack(">II",data[16:24])==(expected,expected),
          "ICON_"+name.replace(".","_").upper())

check(MANIFEST.get("agent_version") == "0.3.41" and
      'AGENT_VERSION = "0.3.43"' in (PUBLIC / "agent/linux.py").read_text(),
      "SIGNED_PUBLIC_RELEASE_SEPARATE_FROM_CANDIDATE")
print("COMMANDER_CLOUD_LAUNCH_SOURCE_ACCEPTANCE=PASS")
print("COMMANDER_CLOUD_LAUNCH_CHATGPT_OAUTH_E2E=NOT_YET_VERIFIED")
print("COMMANDER_CLOUD_LAUNCH_PLUGIN_DIRECTORY_STATUS=DRAFT_NOT_SUBMITTED")
