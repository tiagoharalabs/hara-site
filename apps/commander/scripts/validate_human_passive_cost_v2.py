#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "public" / "app.js").read_text()

assert "const PORTAL_DASHBOARD_CACHE_MS = 30 * 1000;" in APP
assert "const PORTAL_DEVICES_CACHE_MS = 15 * 1000;" in APP
assert "dashboardCache = null;" in APP
assert "devicesCache = null;" in APP

guest = APP.split("function setGuestHeader()", 1)[1].split(
    "function setAuthenticatedHeader", 1
)[0]
assert "dashboardCache = null;" in guest
assert "devicesCache = null;" in guest

dashboard = APP.split("async function loadProductDashboard", 1)[1].split(
    "function copySidebars", 1
)[0]
assert "Date.now() - dashboardCacheAt < PORTAL_DASHBOARD_CACHE_MS" in dashboard
assert "dashboardCache = payload;" in dashboard

devices = APP.split("async function loadDevices", 1)[1].split(
    "function armPairingExpiry", 1
)[0]
assert "Date.now() - devicesCacheAt < PORTAL_DEVICES_CACHE_MS" in devices
assert "const forceRefresh = force || Boolean(trigger);" in devices
assert "devicesCache = payload;" in devices

route = APP.split("function route(target", 1)[1].split(
    "copySidebars();", 1
)[0]
devices_route = route.split('if (next === "devices")', 1)[1].split(
    "} else if", 1
)[0]
assert "hydrateSessionHeader()" not in devices_route
assert "loadDevices();" in devices_route

assert "await loadDevices(null, true);" in APP
assert 'if (appViews.has(initialRoute)) {' in APP

# The only interval is the local pairing-expiry countdown; no network poll loop.
assert APP.count("setInterval(") == 1
interval = APP.split("setInterval(", 1)[0].rsplit("const tick", 1)[1]
assert "fetch(" not in interval

print("COMMANDER_HUMAN_PASSIVE_DASHBOARD_TTL=PASS")
print("COMMANDER_HUMAN_PASSIVE_DEVICES_TTL=PASS")
print("COMMANDER_HUMAN_MUTATION_FORCE_REFRESH=PASS")
print("COMMANDER_HUMAN_BACKGROUND_NETWORK_POLLING=ABSENT")
