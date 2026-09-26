#!/usr/bin/env python3
"""Bounded DEV-only Event V2 burst probe.

Runs a small concurrent set of hara.health calls through the existing DEV wake
probe contract. Output is metadata-only; token and result payloads are never
printed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import statistics
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAKE_PROBE = HERE / "commander_event_v2_dev_wake_probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("hara_event_v2_wake_probe", WAKE_PROBE)
    if spec is None or spec.loader is None:
        raise RuntimeError("BURST_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_probe()


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return int(ordered[index])


def run_one(
    token: str,
    subject: str,
    device_id: str,
    timeout: float,
    busy_retries: int,
) -> dict:
    started = time.monotonic()
    retries_used = 0
    while True:
        try:
            result = probe.run_probe(token, subject, device_id, timeout)
            result = dict(result)
            result["wall_ms"] = int((time.monotonic() - started) * 1000)
            result["busy_retries"] = retries_used
            return result
        except probe.ProbeError as exc:
            if str(exc) != "DEVICE_BUSY" or retries_used >= busy_retries:
                raise
            retry_ms = int(getattr(exc, "retry_after_ms", 0) or 1000)
            time.sleep(max(0.05, retry_ms / 1000.0))
            retries_used += 1


def run_burst(
    token: str,
    subject: str,
    device_id: str,
    concurrency: int,
    timeout: float,
    busy_retries: int = 0,
) -> dict:
    if concurrency < 1 or concurrency > 20:
        raise RuntimeError("BURST_CONCURRENCY_INVALID")

    started = time.monotonic()
    results = []
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(run_one, token, subject, device_id, timeout, busy_retries)
            for _ in range(concurrency)
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(type(exc).__name__ + ":" + str(exc))

    wall_ms = int((time.monotonic() - started) * 1000)
    latencies = [int(row["latency_ms"]) for row in results]
    polls = [int(row["status_polls"]) for row in results]

    return {
        "requested": concurrency,
        "completed": len(results),
        "failed": len(errors),
        "wall_ms": wall_ms,
        "latency_min_ms": min(latencies) if latencies else 0,
        "latency_median_ms": int(statistics.median(latencies)) if latencies else 0,
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_max_ms": max(latencies) if latencies else 0,
        "status_polls_total": sum(polls),
        "terminal_from_enqueue": sum(
            1 for row in results if bool(row.get("terminal_from_enqueue"))
        ),
        "busy_retries_total": sum(
            int(row.get("busy_retries") or 0) for row in results
        ),
        "error_classes": sorted(set(errors)),
    }


def self_check() -> None:
    assert WAKE_PROBE.is_file()
    assert percentile([1, 2, 3, 4], 0.95) == 4
    assert percentile([5], 0.95) == 5
    assert probe.ProbeError("DEVICE_BUSY", 1000).retry_after_ms == 1000
    print("COMMANDER_EVENT_V2_DEV_BURST_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_DEV_BURST_MAX_CONCURRENCY=20")
    print("COMMANDER_EVENT_V2_DEV_BURST_CUSTOMER_CONTENT_OUTPUT=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--subject")
    parser.add_argument("--device-id")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--busy-retries", type=int, default=0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if not args.token_file or not args.subject or not args.device_id:
        parser.error("--token-file, --subject and --device-id are required")

    token = probe.load_token(Path(args.token_file))
    try:
        result = run_burst(
            token,
            args.subject.strip(),
            args.device_id.strip(),
            args.concurrency,
            args.timeout,
            args.busy_retries,
        )
    finally:
        token = ""

    print("COMMANDER_EVENT_V2_DEV_BURST_REQUESTED=" + str(result["requested"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_COMPLETED=" + str(result["completed"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_FAILED=" + str(result["failed"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_WALL_MS=" + str(result["wall_ms"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_LATENCY_MIN_MS=" + str(result["latency_min_ms"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_LATENCY_MEDIAN_MS=" + str(result["latency_median_ms"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_LATENCY_P95_MS=" + str(result["latency_p95_ms"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_LATENCY_MAX_MS=" + str(result["latency_max_ms"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_STATUS_POLLS_TOTAL=" + str(result["status_polls_total"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_TERMINAL_FROM_ENQUEUE=" + str(result["terminal_from_enqueue"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_BUSY_RETRIES_TOTAL=" + str(result["busy_retries_total"]))
    print("COMMANDER_EVENT_V2_DEV_BURST_TOKEN_EXPOSED=FALSE")
    if result["error_classes"]:
        print("COMMANDER_EVENT_V2_DEV_BURST_ERROR_CLASSES=" + ",".join(result["error_classes"]))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
