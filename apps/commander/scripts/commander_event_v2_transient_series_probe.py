#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE_PROBE = HERE / "commander_event_v2_transient_live_probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("hara_transient_live_probe", LIVE_PROBE)
    if spec is None or spec.loader is None:
        raise RuntimeError("SERIES_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def summarize(values: list[float]) -> dict:
    return {
        "min_ms": min(values),
        "p50_ms": statistics.median(values),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
        "mean_ms": statistics.mean(values),
    }


def self_check() -> None:
    sample = [1.0, 2.0, 3.0, 4.0, 5.0]
    stats = summarize(sample)
    assert stats["min_ms"] == 1.0
    assert stats["p50_ms"] == 3.0
    assert stats["p95_ms"] == 5.0
    assert stats["p99_ms"] == 5.0
    assert stats["max_ms"] == 5.0
    probe = load_probe()
    probe.self_check()
    print("COMMANDER_TRANSIENT_SERIES_PROBE_SOURCE=PASS")
    print("COMMANDER_TRANSIENT_SERIES_PROBE_TOKEN_OUTPUT=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--subject")
    parser.add_argument("--device-id")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.token_file or not args.subject or not args.device_id or not args.output:
        parser.error("--token-file, --subject, --device-id and --output are required")
    if args.count < 1 or args.count > 1000:
        raise RuntimeError("SERIES_COUNT_INVALID")

    probe = load_probe()
    token = probe.load_token(Path(args.token_file))
    rows = []
    try:
        for index in range(1, args.count + 1):
            proof = probe.run(
                token,
                args.subject.strip(),
                args.device_id.strip(),
                args.timeout,
            )
            row = {
                "index": index,
                "request_id": proof["request_id"],
                "health_ms": proof["health_ms"],
                "invoke_ms": proof["invoke_ms"],
                "replay_ms": proof["replay_ms"],
                "cycle_ms": proof["cycle_ms"],
                "commit_state": proof["commit_state"],
                "replay_mode": proof["replay_mode"],
                "replay_outcome": proof["replay_outcome"],
            }
            rows.append(row)
            print(
                f"SERIES_RUN_{index}=PASS "
                f"health_ms={row['health_ms']:.1f} "
                f"invoke_ms={row['invoke_ms']:.1f} "
                f"replay_ms={row['replay_ms']:.1f} "
                f"cycle_ms={row['cycle_ms']:.1f}",
                flush=True,
            )
    finally:
        token = ""

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "hara.commander-event-v2-transient-series.v1",
        "count": len(rows),
        "health": summarize([r["health_ms"] for r in rows]),
        "invoke": summarize([r["invoke_ms"] for r in rows]),
        "replay": summarize([r["replay_ms"] for r in rows]),
        "cycle": summarize([r["cycle_ms"] for r in rows]),
        "rows": rows,
    }
    output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print("COMMANDER_TRANSIENT_SERIES=PASS")
    print("COMMANDER_TRANSIENT_SERIES_COUNT=" + str(len(rows)))
    for name in ("health", "invoke", "replay", "cycle"):
        stats = payload[name]
        prefix = "COMMANDER_TRANSIENT_SERIES_" + name.upper()
        print(prefix + "_P50_MS=" + f"{stats['p50_ms']:.3f}")
        print(prefix + "_P95_MS=" + f"{stats['p95_ms']:.3f}")
        print(prefix + "_P99_MS=" + f"{stats['p99_ms']:.3f}")
        print(prefix + "_MAX_MS=" + f"{stats['max_ms']:.3f}")
    print("COMMANDER_TRANSIENT_SERIES_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
