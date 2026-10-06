# H.A.R.A. Commander — Support plane V1

Date: 2026-10-06
State: SOURCE/PREPROD PASS — DEV LIVE PENDING

## Goal

Turn the existing sanitized hara.commander-support-report.v2 into a bounded,
tenant-scoped support workflow without storing raw customer command, payload or
result content.

## Storage

Migration:
- 0028_support_reports.sql

Retention:
- 30 days
- scheduled purge
- maximum 500 expired rows per maintenance run

Stored report:
- re-sanitized server-side from an explicit allowlist
- maximum 16 KiB after sanitization
- device must be ACTIVE and belong to the authenticated tenant
- submitter subject and tenant are taken from the authenticated portal session

Allowed metadata includes:
- device/platform/Agent version
- heartbeat and sanitized error class
- 24h aggregate SLO/latency metadata
- product lease plan/mode/expiry with signed-token presence boolean only
- local budget counters/state without lease token
- operations DB size/mode
- up to 10 receipt SHA-256 identifiers

Explicitly excluded:
- command text
- arguments
- payload/result values
- stdout/stderr
- device token
- product lease token
- arbitrary logs/files

## Portal surface

OWNER/ADMIN only:
- GET /api/portal/support-reports
- POST /api/portal/support-reports
- POST /api/portal/support-reports/delete

Mutations retain the normal portal origin and rate-limit guards.

## Source/preprod

PASS:
- migration table and tenant/device/expiry indexes
- no raw payload/result columns
- privacy flags fail closed
- 16 KiB sanitized cap
- receipt hash cap
- device/tenant binding
- tenant-scoped list/delete
- 30-day retention
- bounded purge
- full Commander preprod readiness

## DEV live proof

Worker:
- 4df21d89-20b7-493e-a1f3-ac7dc9a3046d

Migration:
- 0028_support_reports.sql applied to DEV

Live canary:
- privacy-invalid report rejected: PASS
- server-side sanitizer: PASS
- OWNER list: PASS
- cross-tenant list: DENIED
- cross-tenant delete: DENIED
- D1 stored JSON contains no injected raw command/payload/stdout: PASS
- receipt hash filter: PASS
- owner delete: PASS
- fixture cleanup: PASS

COMMANDER_SUPPORT_PLANE_DEV=CLOSED_PASS

## PROD live proof

Worker:
- 996e1bbd-dd48-4a53-96c4-5a058da0bb1c
- rollback: f21917b0-b02e-46f4-aad6-fb0f333643ca

Migration:
- 0028_support_reports.sql applied to PROD
- no pending migrations after rollout

Acceptance:
- versioned promotion preflight PASS
- required secrets PASS
- trigger sync PASS
- Worker promotion PASS
- deployment readback PASS
- full PROD fail-closed suite PASS
- support table rows at rollout: 0
- unauthenticated support list: 401 AUTH_REQUIRED
- unauthenticated delete with correct origin: 401 AUTH_REQUIRED

COMMANDER_SUPPORT_PLANE_PROD=CLOSED_PASS
