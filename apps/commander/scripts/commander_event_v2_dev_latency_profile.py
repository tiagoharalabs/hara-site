#!/usr/bin/env python3
"""Measure DEV Event V2 wake latency without emitting customer payloads.

This probe imports the canonical single-call DEV wake probe, runs a bounded
sequential sample, and emits only aggregate operational metrics suitable for the
Commander NOC baseline.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAKE_PROBE = HERE / "commander_event_v2_dev_wake_probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("hara_event_v2_wake_probe", WAKE_PROBE)
    if spec is None or spec.loader is None:
        raise RuntimeError("LATENCY_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        raise RuntimeError("LATENCY_SAMPLE_EMPTY")
    if not 0.0 <= fraction <= 1.0:
        raise RuntimeError("LATENCY_PERCENTILE_INVALID")
    ordered = sorted(int(v) for v in values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def summarize(samples: list[dict]) -> dict:
    if not samples:
        raise RuntimeError("LATENCY_SAMPLE_EMPTY")

    latencies = [int(s["latency_ms"]) for s in samples]
    enqueue = [int(s["enqueue_ms"]) for s in samples]
    terminal = [int(s["terminal_after_enqueue_ms"]) for s in samples]
    polls = [int(s["status_polls"]) for s in samples]
    direct = sum(1 for s in samples if bool(s["terminal_from_enqueue"]))

    return {
        "samples": len(samples),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_p99_ms": percentile(latencies, 0.99),
        "latency_mean_ms": int(round(statistics.fmean(latencies))),
        "enqueue_p50_ms": percentile(enqueue, 0.50),
        "terminal_after_enqueue_p50_ms": percentile(terminal, 0.50),
        "status_polls_total": sum(polls),
        "status_polls_per_call": round(sum(polls) / len(samples), 3),
        "terminal_from_enqueue_count": direct,
        "terminal_from_enqueue_fraction": round(direct / len(samples), 4),
    }


def self_check() -> None:
    sample = [
        {
            "latency_ms": 1000,
            "enqueue_ms": 600,
            "terminal_after_enqueue_ms": 400,
            "status_polls": 0,
            "terminal_from_enqueue": True,
        },
        {
            "latency_ms": 1500,
            "enqueue_ms": 700,
            "terminal_after_enqueue_ms": 800,
            "status_polls": 1,
            "terminal_from_enqueue": False,
        },
        {
            "latency_ms": 2000,
            "enqueue_ms": 800,
            "terminal_after_enqueue_ms": 1200,
            "status_polls": 2,
            "terminal_from_enqueue": False,
        },
        {
            "latency_ms": 2500,
            "enqueue_ms": 900,
            "terminal_after_enqueue_ms": 1600,
            "status_polls": 0,
            "terminal_from_enqueue": True,
        },
    ]
    summary = summarize(sample)
    assert summary["latency_p50_ms"] == 1500
    assert summary["latency_p95_ms"] == 2500
    assert summary["latency_p99_ms"] == 2500
    assert summary["status_polls_total"] == 3
    assert summary["status_polls_per_call"] == 0.75
    assert summary["terminal_from_enqueue_count"] == 2
    assert summary["terminal_from_enqueue_fraction"] == 0.5

    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "result_json",
        "command_payload",
        "customer_file",
        "Authorization:",
        "Cookie:",
    )
    for token in forbidden:
        assert token not in source

    print("COMMANDER_EVENT_V2_LATENCY_PROFILE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_LATENCY_PROFILE_AGGREGATE_ONLY=TRUE")
    print("COMMANDER_EVENT_V2_LATENCY_PROFILE_PAYLOAD_OUTPUT=ABSENT")


def execute(args) -> int:
    probe = load_probe()
    token = probe.load_token(Path(args.token_file))
    samples: list[dict] = []
    failures = 0

    try:
        for _ in range(args.samples):
            try:
                samples.append(
                    probe.run_probe(
                        token,
                        args.subject.strip(),
                        args.device_id.strip(),
                        args.timeout,
                    )
                )
            except Exception:
                failures += 1
    finally:
        token = ""

    attempted = args.samples
    success = len(samples)
    failure_fraction = failures / attempted if attempted else 1.0

    if success < args.min_success_samples:
        raise RuntimeError("LATENCY_PROFILE_INSUFFICIENT_SUCCESS")
    summary = summarize(samples)

    print("COMMANDER_EVENT_V2_LATENCY_PROFILE=PASS")
    print("COMMANDER_EVENT_V2_LATENCY_SAMPLES_ATTEMPTED=" + str(attempted))
    print("COMMANDER_EVENT_V2_LATENCY_SAMPLES_SUCCESS=" + str(success))
    print("COMMANDER_EVENT_V2_LATENCY_SAMPLES_FAILED=" + str(failures))
    print("COMMANDER_EVENT_V2_LATENCY_FAILURE_FRACTION=" + f"{failure_fraction:.4f}")
    print("COMMANDER_EVENT_V2_LATENCY_P50_MS=" + str(summary["latency_p50_ms"]))
    print("COMMANDER_EVENT_V2_LATENCY_P95_MS=" + str(summary["latency_p95_ms"]))
    print("COMMANDER_EVENT_V2_LATENCY_P99_MS=" + str(summary["latency_p99_ms"]))
    print("COMMANDER_EVENT_V2_LATENCY_MEAN_MS=" + str(summary["latency_mean_ms"]))
    print("COMMANDER_EVENT_V2_ENQUEUE_P50_MS=" + str(summary["enqueue_p50_ms"]))
    print(
        "COMMANDER_EVENT_V2_TERMINAL_AFTER_ENQUEUE_P50_MS="
        + str(summary["terminal_after_enqueue_p50_ms"])
    )
    print("COMMANDER_EVENT_V2_STATUS_POLLS_TOTAL=" + str(summary["status_polls_total"]))
    print(
        "COMMANDER_EVENT_V2_STATUS_POLLS_PER_CALL="
        + str(summary["status_polls_per_call"])
    )
    print(
        "COMMANDER_EVENT_V2_TERMINAL_FROM_ENQUEUE_FRACTION="
        + str(summary["terminal_from_enqueue_fraction"])
    )
    print("COMMANDER_EVENT_V2_LATENCY_PAYLOAD_OUTPUT=ABSENT")
    print("COMMANDER_EVENT_V2_LATENCY_TOKEN_EXPOSED=FALSE")

    if failure_fraction > args.max_failure_fraction:
        print("COMMANDER_EVENT_V2_LATENCY_REGRESSION=FAIL_FAILURE_RATE")
        return 2
    if summary["latency_p95_ms"] > args.max_p95_ms:
        print("COMMANDER_EVENT_V2_LATENCY_REGRESSION=FAIL_P95")
        return 3
    if summary["status_polls_per_call"] > args.max_status_polls_per_call:
        print("COMMANDER_EVENT_V2_LATENCY_REGRESSION=FAIL_STATUS_POLLS")
        return 4

    print("COMMANDER_EVENT_V2_LATENCY_REGRESSION=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--subject")
    parser.add_argument("--device-id")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--min-success-samples", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-p95-ms", type=int, default=3500)
    parser.add_argument("--max-failure-fraction", type=float, default=0.05)
    parser.add_argument("--max-status-polls-per-call", type=float, default=1.0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if not args.token_file or not args.subject or not args.device_id:
        parser.error("--token-file, --subject and --device-id are required")
    if args.samples < 5 or args.samples > 200:
        raise RuntimeError("LATENCY_SAMPLE_COUNT_INVALID")
    if args.min_success_samples < 5 or args.min_success_samples > args.samples:
        raise RuntimeError("LATENCY_MIN_SUCCESS_INVALID")
    if args.timeout < 2 or args.timeout > 30:
        raise RuntimeError("LATENCY_TIMEOUT_INVALID")
    if not 0 <= args.max_failure_fraction <= 1:
        raise RuntimeError("LATENCY_FAILURE_THRESHOLD_INVALID")
    if args.max_p95_ms < 500:
        raise RuntimeError("LATENCY_P95_THRESHOLD_INVALID")
    if args.max_status_polls_per_call < 0:
        raise RuntimeError("LATENCY_POLL_THRESHOLD_INVALID")

    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
