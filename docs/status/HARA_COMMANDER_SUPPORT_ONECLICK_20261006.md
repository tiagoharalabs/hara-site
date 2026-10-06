# H.A.R.A. Commander — One-click sanitized support

Date: 2026-10-06
Agent release: 0.3.39

## Goal

Remove manual copy/paste from the support workflow while preserving the
local-first privacy boundary.

Flow:

1. authenticated OWNER/ADMIN clicks Enviar diagnóstico;
2. browser asks for loopback permission only because the user explicitly
   clicked;
3. portal fetches http://127.0.0.1:32145/v1/support with credentials omitted;
4. local Agent builds hara.commander-support-report.v2;
5. browser verifies all privacy flags are false;
6. portal posts the report with same-origin session auth to
   /api/portal/support-reports;
7. Worker re-sanitizes from its explicit allowlist, binds tenant/device and
   persists the bounded report for 30 days.

The localhost endpoint is an accelerator/data source only. Cloud identity,
tenant authorization and support-plane persistence authority remain unchanged.

## Privacy

The local report contains no:
- device token
- product lease token
- command text
- arguments
- raw payload/result
- stdout/stderr
- arbitrary log/file content

Local /v1/support:
- loopback bind only
- exact Commander Origin CORS allowlist
- Private Network Access header
- foreign Origin -> 403 LOCAL_ORIGIN_DENIED

The browser uses:
- credentials omitted for localhost
- targetAddressSpace loopback
- same-origin session credentials for cloud submit
- OWNER/ADMIN UI gate
- explicit privacy-flag precheck

The Worker still performs the authoritative privacy re-sanitization.

## Source / preprod

PASS:
- reusable Agent support report builder
- loopback /v1/support
- portal button/status
- browser permission model
- local credentials omitted
- cloud auth preserved
- privacy precheck
- server privacy sanitizer
- support plane tenant/device binding
- support report 16 KiB cap
- 30-day retention
- signed release manifest 0.3.39
- clean Linux lifecycle
- full E2E
- full preprod readiness

## DEV live proof

Worker:
- 6f20e118-17c6-4442-a274-737550b308cb
- rollback: 27ec7858-fef0-48b2-8bb5-ce9e5f1b6864

Public assets:
- cache key 20261006-support1 PASS
- support button PASS
- portal local support fetch wiring PASS
- portal privacy gate PASS
- portal cloud POST wiring PASS
- served Agent release 0.3.39 PASS
- served Agent SHA matches manifest PASS

Live support plane canary:
- privacy-invalid report rejected PASS
- server sanitizer PASS
- OWNER list PASS
- cross-tenant list DENIED
- cross-tenant delete DENIED
- D1 stored JSON sanitized PASS
- owner delete PASS
- cleanup PASS

Live served-Agent loopback canary:
- /v1/support HTTP 200
- schema hara.commander-support-report.v2
- exact DEV Origin allowed
- PNA header true
- device token absent
- privacy flags safe
- evil Origin -> 403 LOCAL_ORIGIN_DENIED

## State

SUPPORT_ONECLICK_SOURCE=CLOSED_PASS
SUPPORT_ONECLICK_PREPROD=CLOSED_PASS
SUPPORT_ONECLICK_DEV=CLOSED_PASS
SUPPORT_ONECLICK_PROD=PENDING
