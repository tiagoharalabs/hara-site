#!/usr/bin/env python3
"""Bounded DEV-only Event V2 multi-device transient concurrency probe.

Consumes a metadata-only manifest produced by commander_event_v2_dev_multidevice_lab.py
and one existing DEV MCP product-token file. Every device uses its own subject and
selected device. Output is aggregate-only: no request IDs, receipts, device IDs,
tokens, payloads, results, or customer content are emitted.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import stat
import statistics
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE_PROBE = HERE / "commander_event_v2_transient_live_probe.py"
MAX_DEVICES = 10
MAX_WAVES = 5


class ProbeError(RuntimeError):
    pass


def load_live_probe():
    spec = importlib.util.spec_from_file_location(
        "hara_event_v2_transient_live_probe", LIVE_PROBE
    )
    if spec is None or spec.loader is None:
        raise ProbeError("MULTIDEVICE_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = load_live_probe()


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return float(ordered[index])


def load_manifest(path: Path) -> dict:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ProbeError("MULTIDEVICE_MANIFEST_FILE_INVALID")
    if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
        raise ProbeError("MULTIDEVICE_MANIFEST_PERMISSIONS")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("schema") != "hara.commander-event-v2-multidevice-lab.v1":
        raise ProbeError("MULTIDEVICE_MANIFEST_SCHEMA_INVALID")
    if obj.get("environment") != "DEV":
        raise ProbeError("MULTIDEVICE_MANIFEST_ENV_INVALID")
    devices = obj.get("devices")
    if not isinstance(devices, list) or not 2 <= len(devices) <= MAX_DEVICES:
        raise ProbeError("MULTIDEVICE_MANIFEST_COUNT_INVALID")
    subjects, device_ids = [], []
    for row in devices:
        if not isinstance(row, dict):
            raise ProbeError("MULTIDEVICE_MANIFEST_DEVICE_INVALID")
        subject = str(row.get("subject") or "").strip()
        device_id = str(row.get("device_id") or "").strip()
        if not subject or not device_id.startswith("HARA-DEVICE-"):
            raise ProbeError("MULTIDEVICE_MANIFEST_DEVICE_INVALID")
        subjects.append(subject)
        device_ids.append(device_id)
    if len(set(subjects)) != len(subjects) or len(set(device_ids)) != len(device_ids):
        raise ProbeError("MULTIDEVICE_MANIFEST_DUPLICATE")
    lowered = json.dumps(obj).lower()
    if "device_token" in lowered or "pairing_token" in lowered:
        raise ProbeError("MULTIDEVICE_MANIFEST_SECRET_FIELD")
    return obj


def run_one(token: str, subject: str, device_id: str, timeout: float) -> dict:
    proof = live.run(token, subject, device_id, timeout)
    return {
        "health_ms": float(proof["health_ms"]),
        "invoke_ms": float(proof["invoke_ms"]),
        "replay_ms": float(proof["replay_ms"]),
        "cycle_ms": float(proof["cycle_ms"]),
        "commit_state": str(proof["commit_state"]),
        "replay_mode": str(proof["replay_mode"]),
        "replay_outcome": str(proof["replay_outcome"]),
        "payload_persisted": bool(proof["payload_persisted"]),
        "result_persisted": bool(proof["result_persisted"]),
        "learning_content": bool(proof["learning_content"]),
    }


def safe_error(exc: Exception) -> str:
    code = str(exc).strip()
    if not code:
        code = type(exc).__name__
    # Existing live probe emits bounded error codes. Refuse arbitrary verbose text.
    if len(code) > 160 or any(ch in code for ch in ("\n", "\r", "{", "}")):
        return type(exc).__name__
    return type(exc).__name__ + ":" + code


def run_wave(token: str, devices: list[dict], timeout: float) -> dict:
    started = time.perf_counter()
    results, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as pool:
        futures = [
            pool.submit(run_one, token, str(row["subject"]), str(row["device_id"]), timeout)
            for row in devices
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(safe_error(exc))
    return {
        "requested": len(devices),
        "completed": len(results),
        "failed": len(errors),
        "wall_ms": (time.perf_counter() - started) * 1000.0,
        "results": results,
        "error_classes": sorted(set(errors)),
    }


def summarize(waves: list[dict]) -> dict:
    rows = [row for wave in waves for row in wave["results"]]
    cycles = [row["cycle_ms"] for row in rows]
    invokes = [row["invoke_ms"] for row in rows]
    replays = [row["replay_ms"] for row in rows]
    privacy_failures = sum(
        1 for row in rows
        if row["payload_persisted"] or row["result_persisted"] or row["learning_content"]
    )
    semantic_failures = sum(
        1 for row in rows
        if row["commit_state"] != "COMMITTED"
        or row["replay_mode"] != "REPLAY_ONLY"
        or row["replay_outcome"] != "REPLAYED"
    )
    return {
        "requested": sum(w["requested"] for w in waves),
        "completed": len(rows),
        "failed": sum(w["failed"] for w in waves),
        "wave_wall_max_ms": max((w["wall_ms"] for w in waves), default=0.0),
        "cycle_p50_ms": statistics.median(cycles) if cycles else 0.0,
        "cycle_p95_ms": percentile(cycles, 0.95),
        "cycle_p99_ms": percentile(cycles, 0.99),
        "invoke_p95_ms": percentile(invokes, 0.95),
        "replay_p95_ms": percentile(replays, 0.95),
        "privacy_failures": privacy_failures,
        "semantic_failures": semantic_failures,
        "error_classes": sorted({e for w in waves for e in w["error_classes"]}),
    }


def self_check() -> None:
    assert LIVE_PROBE.is_file()
    assert MAX_DEVICES == 10
    assert MAX_WAVES == 5
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    source = Path(__file__).read_text(encoding="utf-8")
    print_lines = "\n".join(
        line for line in source.splitlines()
        if "print(" in line and "TOKEN_EXPOSED" not in line
    )
    assert "token" not in print_lines.lower()
    assert "request_id" not in print_lines
    assert "receipt_sha256" not in print_lines
    forbidden_prod = "https://commander." + "haralabs.com.br"
    assert forbidden_prod not in source
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROBE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROBE_MAX_DEVICES=10")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROBE_AGGREGATE_OUTPUT=TRUE")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROBE_CUSTOMER_CONTENT_OUTPUT=ABSENT")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROBE_PROD_MUTATION=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--token-file")
    parser.add_argument("--waves", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if not args.manifest or not args.token_file:
        parser.error("--manifest and --token-file are required")
    if not 1 <= args.waves <= MAX_WAVES:
        raise ProbeError("MULTIDEVICE_WAVES_INVALID")
    if not 5 <= args.timeout <= 40:
        raise ProbeError("MULTIDEVICE_TIMEOUT_INVALID")

    manifest = load_manifest(Path(args.manifest))
    token = live.load_token(Path(args.token_file))
    waves = []
    try:
        for _ in range(args.waves):
            waves.append(run_wave(token, manifest["devices"], args.timeout))
    finally:
        token = ""

    summary = summarize(waves)
    expected = len(manifest["devices"]) * args.waves
    passed = (
        summary["completed"] == expected
        and summary["failed"] == 0
        and summary["privacy_failures"] == 0
        and summary["semantic_failures"] == 0
    )

    print("COMMANDER_EVENT_V2_MULTIDEVICE_LIVE=" + ("PASS" if passed else "FAIL"))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_DEVICES=" + str(len(manifest["devices"])))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_WAVES=" + str(args.waves))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_REQUESTED_CYCLES=" + str(summary["requested"]))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_COMPLETED_CYCLES=" + str(summary["completed"]))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_FAILED_CYCLES=" + str(summary["failed"]))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_WAVE_WALL_MAX_MS=" + f"{summary['wave_wall_max_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_CYCLE_P50_MS=" + f"{summary['cycle_p50_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_CYCLE_P95_MS=" + f"{summary['cycle_p95_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_CYCLE_P99_MS=" + f"{summary['cycle_p99_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_INVOKE_P95_MS=" + f"{summary['invoke_p95_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_REPLAY_P95_MS=" + f"{summary['replay_p95_ms']:.3f}")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PRIVACY_FAILURES=" + str(summary["privacy_failures"]))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_SEMANTIC_FAILURES=" + str(summary["semantic_failures"]))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_ERROR_CLASSES=" + (
        ",".join(summary["error_classes"]) if summary["error_classes"] else "NONE"
    ))
    print("COMMANDER_EVENT_V2_MULTIDEVICE_TOKEN_EXPOSED=FALSE")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProbeError, live.ProbeError) as exc:
        print("COMMANDER_EVENT_V2_MULTIDEVICE_LIVE=FAIL:" + safe_error(exc))
        raise SystemExit(1)
