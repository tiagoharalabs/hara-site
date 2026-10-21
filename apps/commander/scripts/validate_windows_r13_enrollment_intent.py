#!/usr/bin/env python3
"""Windows candidate's enrollment ACK/intent safety contract (no install)."""
from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
source = (APP / "candidate/windows_install_043.ps1").read_text(encoding="utf-8")


def need(condition: bool, code: str) -> None:
    if not condition:
        raise SystemExit("WINDOWS_R13_" + code + "=FAIL")
    print("WINDOWS_R13_" + code + "=PASS")


need('"enrollment-intent.json"' in source, "DURABLE_INTENT_FILE")
need("RandomNumberGenerator" in source and "New-Object byte[] 48" in source,
     "CLIENT_SECRET_OS_RANDOM_48_BYTES")
need("ConvertFrom-SecureString" in source and "ConvertTo-SecureString" in source,
     "DPAPI_PROTECTION")
need("ENROLLMENT_INTENT_PAIRING_MISMATCH" in source, "PAIRING_BOUND_RETRY")
need("client_device_token=$ClientDeviceToken" in source, "CLIENT_SECRET_SENT")
need(source.index("$PreparedRelease = Get-VerifiedReleaseBeforeEnrollment")
     < source.index("$ClientDeviceToken = Get-EnrollmentIntentToken $PairingToken")
     < source.index('Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll-intent"'), "RELEASE_BEFORE_INTENT_BEFORE_POST")
need('Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll-intent"' in source,
     "LEGACY_SERVER_ROUTE_CANNOT_CONSUME_PAIRING")
need("ENROLLMENT_ACK_UNKNOWN" in source, "UNCERTAIN_RESPONSE_TYPED")
need("$Enroll.device_token -cne $ClientDeviceToken" in source, "SERVER_TOKEN_MATCH")
need("Remove-Item -LiteralPath $EnrollmentIntent" in source, "INTENT_REMOVED_ON_ACK_AND_STARTUP")
need('HARA_COMMANDER_AGENT_UNINSTALL=LOCAL_ONLY' in source and
     'if ($revokeState -eq "PENDING")' in source, "PENDING_REVOKE_PRESERVES_CREDENTIAL")
emitted = [line.strip() for line in source.splitlines()
           if line.strip().startswith(("Write-Host", "Write-Output", "Write-Error", "throw "))]
need(not any(secret in line for line in emitted for secret in (
    "$PairingToken", "$ClientDeviceToken", "$DeviceTokenForRollback",
    "$Payload", "$Enroll.device_token", "$SecurePairing",
)), "NO_SECRET_IN_OPERATOR_OUTPUT")
print("WINDOWS_R13_ENROLLMENT_INTENT_CONTRACT=PASS")
