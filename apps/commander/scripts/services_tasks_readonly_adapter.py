#!/usr/bin/env python3
"""H.A.R.A. Commander -> HARA Services native queue status: read-only adapter.

The signed Commander agent deliberately runs with NoNewPrivileges=yes, so it
cannot elevate through the protected Services sudo queue helper. Rather than
alter that sandbox or the AFS-pinned canonical command, this sidecar invokes
one exact READ-ONLY canonical CLI operation over existing host-key-verified SSH
to the native Services host. It never accepts a user-supplied shell command.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

SCHEMA = "hara.contact-tasks.result.v1"
HOSTNAME = "services"
HOST = "sartorius@services"
TIMEOUT_SECONDS = 18
SSH_COMMAND = [
    "/usr/bin/ssh", "-n", "-T",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=5",
    "-o", "ConnectionAttempts=1",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ClearAllForwardings=yes",
    "-o", "ForwardAgent=no",
    "-o", "ForwardX11=no",
    "-o", "PermitLocalCommand=no",
    "-o", "RequestTTY=no",
    "-o", "LogLevel=ERROR",
    HOST,
    # Fixed exact native command. No interpolation or user-controlled arguments.
    "hostname -s && exec /usr/local/bin/hara agents tasks status",
]
FIELDS = ("pending", "running", "complete", "failed")


class UnsafeQueueResult(ValueError):
    pass


def fail(code: str, reason: str, exit_code: int = 2) -> int:
    result = {
        "schema": "hara.commander.services-task-status-adapter.v1",
        "state": "HOLD_NATIVE_SERVICES_QUEUE_STATUS",
        "blocker": {"code": code, "reason": reason},
        "mutation_performed": False,
        "mutation_possible": False,
        "native_authority_not_reached": True,
    }
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return exit_code


def decode_native(stdout: str) -> dict:
    lines = stdout.strip().splitlines()
    # Exactly two lines: native identity and canonical CLI JSON.
    if len(lines) != 2 or lines[0].strip() != HOSTNAME:
        raise UnsafeQueueResult("NATIVE_SERVICES_HOST_IDENTITY_INVALID")
    try:
        obj = json.loads(lines[1])
    except (TypeError, ValueError) as exc:
        raise UnsafeQueueResult("NATIVE_QUEUE_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise UnsafeQueueResult("NATIVE_QUEUE_NOT_OBJECT")
    if obj.get("schema") != SCHEMA or obj.get("authority") != "HARA_SERVICES":
        raise UnsafeQueueResult("CANONICAL_SCHEMA_OR_AUTHORITY_INVALID")
    if obj.get("state") != "READY":
        raise UnsafeQueueResult("NATIVE_QUEUE_NOT_READY")
    if obj.get("mutation_performed") is not False or obj.get("mutation_possible") is not False:
        raise UnsafeQueueResult("NON_READ_ONLY_NATIVE_REPLY")
    if obj.get("domain_receipt_refs") != []:
        raise UnsafeQueueResult("UNEXPECTED_DOMAIN_MUTATION_RECEIPT")
    counts = obj.get("queue_counts")
    if not isinstance(counts, dict):
        raise UnsafeQueueResult("QUEUE_COUNTS_MISSING")
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in FIELDS):
        raise UnsafeQueueResult("QUEUE_COUNTS_INVALID")
    allowed_nodes = obj.get("allowed_nodes")
    allowed_modes = obj.get("allowed_modes")
    if not isinstance(allowed_nodes, list) or not isinstance(allowed_modes, list):
        raise UnsafeQueueResult("QUEUE_CONFIG_FIELDS_INVALID")
    return obj


def self_test() -> None:
    good = {
        "schema": SCHEMA, "authority": "HARA_SERVICES", "state": "READY",
        "mutation_performed": False, "mutation_possible": False,
        "domain_receipt_refs": [],
        "queue_counts": {"pending": 0, "running": 0, "complete": 12, "failed": 1},
        "allowed_modes": ["read-only", "workspace-write"],
        "allowed_nodes": ["nucleo-a"],
    }
    raw = "services\n" + json.dumps(good) + "\n"
    assert decode_native(raw) == good
    for invalid in [
        "attacker\n" + json.dumps(good) + "\n",
        "services\n{}",
        "services\nnot-json",
        "services\n" + json.dumps({**good, "mutation_possible": True}),
        "services\n" + json.dumps({**good, "mutation_performed": True}),
        "services\n" + json.dumps({**good, "authority": "SECONDARY_PLANE"}),
        "services\n" + json.dumps({**good, "queue_counts": {"pending": -1}}),
    ]:
        try:
            decode_native(invalid)
        except UnsafeQueueResult:
            continue
        raise AssertionError("INVALID_NATIVE_REPLY_WAS_ADMITTED")
    print("HARA_COMMANDER_NATIVE_TASK_READ_ONLY_ADAPTER_SELF_TEST=PASS")


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        self_test()
        return 0
    if argv not in ([], ["status"]):
        return fail(
            "READ_ONLY_STATUS_ONLY",
            "Only 'status' is admitted; submit/get/review-submit/review-get require their existing authorized surfaces.",
        )

    if not pathlib.Path("/usr/bin/ssh").is_file():
        return fail("SSH_CLIENT_UNAVAILABLE", "The existing authenticated SSH transport is unavailable.")
    try:
        result = subprocess.run(
            SSH_COMMAND,
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return fail("NATIVE_STATUS_TIMEOUT", "The fixed native Services read timed out.")
    except OSError:
        return fail("NATIVE_STATUS_TRANSPORT_ERROR", "Cannot launch the fixed native Services read.")

    # Never fall back to reading raw queue files or to privileged local sudo.
    if result.returncode != 0:
        return fail(
            "NATIVE_SSH_OR_CANONICAL_CLI_FAILED",
            "Authenticated host-native read was refused or the canonical CLI returned a nonzero result.",
        )
    try:
        data = decode_native(result.stdout)
    except UnsafeQueueResult as exc:
        return fail(str(exc), "Host identity, schema, authority or non-mutating result was not verified.")

    # Preserve the canonical Services status schema unmodified for consumers.
    print(json.dumps(data, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))