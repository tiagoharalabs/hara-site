# H.A.R.A. Commander — Clean Linux lifecycle acceptance

Date: 2026-10-06

## Scope

Hermetic lifecycle proof using the official Linux installer in a completely
empty HOME/XDG environment.

The harness uses:
- real installer script;
- real Agent asset and release manifest;
- real SHA/version/self-test validation;
- real config/file modes/symlinks;
- real installer Python network clients;
- loopback HTTP mock backend for health/enroll/heartbeat/revoke;
- deterministic systemctl shim for user-service state/startup attestation only.

This is stronger than a static test but still does not replace one final truly
fresh external Linux VM before GA.

## Lifecycle proof

PASS:
- clean install from empty HOME;
- pairing token provided through PTY, never echoed;
- device token absent from console output;
- device.env mode 0600;
- Agent mode 0700;
- user unit mode 0600;
- CLI symlink installed;
- support-report.v2 emitted from the fresh install;
- support privacy flags safe;
- stable update integrity/self-test/startup attestation;
- update rollback-ready marker;
- old credential revoked before re-enroll;
- re-enroll refuses still-active authority and accepts revoked authority;
- new device/token replace old enrollment;
- OLD_DEVICE_AUTHORITY_RESURRECTED=FALSE;
- uninstall server self-revoke PASS;
- local config/Agent/unit/CLI cleanup PASS;
- managed hara wrapper absent after uninstall;
- final clean-home lifecycle PASS.

## Regression gate

Scripts:
- apps/commander/scripts/commander_linux_clean_lifecycle.py
- apps/commander/scripts/validate_clean_linux_lifecycle.py

The source contract is now included in validate_preprod_readiness.py.

## State

CLEAN_LINUX_LIFECYCLE_HERMETIC=CLOSED_PASS
CLEAN_LINUX_EXTERNAL_FRESH_VM=PENDING_GA_GATE
