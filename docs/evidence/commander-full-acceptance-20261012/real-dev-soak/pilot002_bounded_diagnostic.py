#!/usr/bin/env python3
"""Owned DEV-only 20-minute diagnostic. No retries or published runtime changes."""
from __future__ import annotations
import concurrent.futures, hashlib, importlib.util, json, os, re, signal, stat, subprocess, threading, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

ROOT = Path("/tmp_hara/commander-win50-utf8-20261012")
APP = ROOT / "apps/commander"
EVIDENCE = ROOT / "docs/evidence/commander-full-acceptance-20261012/real-dev-soak"
RUN_ID = "soak-pilot002-diagnostic-002"
PIN = "97471c0a-b739-4906-90aa-41384a8a1cb1"
PILOT_SECONDS = 1200
LOCK = threading.RLock()
RECORDS = []
TAIL_META = {"enabled": False, "events": 0, "parse_errors": 0, "exception_events": 0}
REPORT = {"schema": "hara.soak-pilot002-bounded-diagnostic.v1", "run_id": RUN_ID,
          "environment": "DEV", "state": "STARTING", "retry_count": 0,
          "max_agents": 2, "pilot_seconds_required": PILOT_SECONDS,
          "root_runner_changed": False, "worker_changed": False, "prod_mutations": False,
          "raw_headers_payloads_messages_saved": False, "requests": RECORDS, "tail": TAIL_META}
DEST = EVIDENCE / "pilot002-diagnostic-002" / "diagnostic-status.json"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def emit():
    with LOCK:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        tmp = DEST.with_suffix(".tmp")
        tmp.write_text(json.dumps(REPORT, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(DEST)

def code(value):
    value = str(value or "")
    return value if re.fullmatch(r"[A-Z][A-Z0-9_:-]{0,159}", value) else "UNCLASSIFIED"

def safe_exception(exception):
    name = str(exception.get("name") or "")
    name = name if name in {"Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "DOMException", "D1Error", "AggregateError"} else "Error"
    message = str(exception.get("message") or "")
    kind = "UNKNOWN"
    for pattern, category in [(r"D1_ERROR.*(?:constraint|UNIQUE|FOREIGN KEY)", "D1_CONSTRAINT"),
                              (r"D1_ERROR.*(?:timeout|timed out)", "D1_TIMEOUT"),
                              (r"(?:Durable Object|DO).*?(?:reset|restart)", "DO_RESET"),
                              (r"(?:WebSocket).*?(?:closed|not open)", "WEBSOCKET_STATE")]:
        if re.search(pattern, message, re.I):
            kind = category
            break
    return {"class": name, "message_sha256": hashlib.sha256(message.encode()).hexdigest(), "safe_cause_class": kind}

def scrub_tail(value):
    event = value.get("event") or {}
    request = event.get("request") or {}
    response = event.get("response") or {}
    outcome = str(value.get("outcome") or "")
    outcome = outcome if outcome in {"ok", "exception", "exceededCpu", "exceededMemory", "canceled", "unknown", "startupFailure"} else "unknown"
    exceptions = [safe_exception(x) for x in value.get("exceptions", []) if isinstance(x, dict)]
    path = urlsplit(str(request.get("url") or "")).path
    path = path if path in {"/api/internal/device/transient-call", "/api/internal/mcp/authorize", "/api/internal/mcp/commit", "/api/internal/mcp/release"} else "OTHER"
    method = str(request.get("method") or "")
    method = method if method in {"POST", "GET"} else "OTHER"
    return {"observed_at_utc": now(), "outcome": outcome, "path": path, "method": method,
            "status": response.get("status") if isinstance(response.get("status"), int) else None,
            "exceptions": exceptions, "logs_discarded": len(value.get("logs") or [])}

def tail_reader(proc, destination):
    decoder = json.JSONDecoder()
    buffer = ""
    with open(destination, "a", encoding="utf-8") as sink:
        os.chmod(destination, 0o600)
        while True:
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            if len(buffer) > 4_000_000:
                buffer = ""
                with LOCK:
                    TAIL_META["parse_errors"] += 1
                    emit()
                continue
            while buffer.strip():
                buffer = buffer.lstrip()
                if not buffer.startswith("{"):
                    end = buffer.find("\n")
                    if end < 0:
                        break
                    buffer = buffer[end + 1:]
                    continue
                try:
                    event, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    break
                buffer = buffer[end:]
                if not isinstance(event, dict):
                    continue
                safe = scrub_tail(event)
                sink.write(json.dumps(safe, sort_keys=True) + "\n")
                sink.flush()
                with LOCK:
                    TAIL_META["events"] += 1
                    TAIL_META["exception_events"] += bool(safe["exceptions"])
                    emit()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

runner_module = module("diagnostic_owned_runner", APP / "scripts/commander_full_acceptance_real_dev_soak.py")
probe = runner_module.probe

def diagnostic_post(path, token, body):
    assert path in {"/api/internal/device/transient-call", "/api/internal/mcp/authorize", "/api/internal/mcp/commit", "/api/internal/mcp/release"}
    request_id = str(body.get("request_id") or "")
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,220}", request_id)
    record = {"request_id": request_id, "path": path, "tool_id": body.get("tool_id"),
              "started_at_utc": now(), "state": "PENDING", "retry_count": 0}
    with LOCK:
        RECORDS.append(record)
        emit()
    started = time.perf_counter()
    req = Request(probe.DEV_ORIGIN + path, data=json.dumps(body, separators=(",", ":"), sort_keys=True).encode(),
                  method="POST", headers={"accept": "application/json", "content-type": "application/json",
                                          "x-hara-mcp-product-token": token,
                                          "x-hara-qa-diagnostic-run": RUN_ID,
                                          "user-agent": "HARA-Commander-OwnedPilot-Diagnostic/1"})
    error = None
    obj = None
    headers = {}
    status = None
    try:
        with urlopen(req, timeout=20) as response:
            status = response.status
            headers = response.headers
            obj = json.loads(response.read() or b"{}")
    except HTTPError as exc:
        status = exc.code
        headers = exc.headers
        try:
            obj = json.loads(exc.read() or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            obj = {}
        error = probe.ProbeError(code(obj.get("code") or "HTTP_" + str(status)))
    except (URLError, TimeoutError) as exc:
        error = probe.ProbeError("QUOTA_PROBE_NETWORK_ERROR")
        record["transport_exception_class"] = type(exc).__name__
    except (json.JSONDecodeError, UnicodeDecodeError):
        error = probe.ProbeError("QUOTA_PROBE_RESPONSE_INVALID")
    finally:
        ray = str(headers.get("cf-ray") or "")
        with LOCK:
            record.update(finished_at_utc=now(), latency_ms=round((time.perf_counter()-started)*1000, 3),
                          http_status=status, cf_ray=ray if re.fullmatch(r"[0-9a-fA-F]{16,32}-[A-Z]{3}", ray) else None,
                          state="FAIL" if error else "PASS", error_code=code(error) if error else None)
            emit()
    if error:
        raise error
    return obj

def preserve_agent_diagnostics(runner):
    summaries = []
    for row in runner.rows:
        log = row["root"] / "agent.log"
        classes = {}
        if log.is_file():
            for line in log.read_text(errors="replace").splitlines():
                match = re.match(r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):", line)
                if match:
                    name = match.group(1)
                    name = name if name in {"RuntimeError", "ValueError", "TypeError", "KeyError", "TimeoutError", "OSError", "ConnectionError", "URLError", "HTTPError", "SSLError", "WebSocketError"} else "OtherException"
                    classes[name] = classes.get(name, 0) + 1
        summaries.append({"index": row["index"], "log_exists_before_cleanup": log.is_file(),
                          "exception_class_counts": classes})
    REPORT["agent_log_safe_summary"] = summaries
    REPORT["agents_before_cleanup"] = runner.connection_snapshot(runner.rows)

def stop_tail(tail):
    if tail and tail.poll() is None:
        os.killpg(tail.pid, signal.SIGTERM)
        try:
            tail.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(tail.pid, signal.SIGKILL)
            tail.wait(timeout=5)

def main():
    runner = None
    tail = None
    tail_thread = None
    terminal = None
    probe.post_json = diagnostic_post
    start = time.monotonic()
    REPORT["started_at_utc"] = now()
    emit()
    try:
        runner = runner_module.Runner(RUN_ID, hours=24, max_agents=2, expected_backend_version=PIN)
        REPORT["backend_at_start"] = runner.audit["backend_at_start"]
        tail_path = runner.home / "tail-sanitized.ndjson"
        tail = subprocess.Popen([str(runner_module.fixtures.fresh.WRANGLER), "tail", "hara-commander-dev-v2",
                                 "--config", str(APP / "wrangler.dev.jsonc"), "--format", "json",
                                 "--sampling-rate", "1", "--version-id", PIN,
                                 "--header", "x-hara-qa-diagnostic-run:" + RUN_ID],
                                cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        TAIL_META["enabled"] = True
        TAIL_META["safe_private_path"] = str(tail_path)
        tail_thread = threading.Thread(target=tail_reader, args=(tail, tail_path), daemon=True)
        tail_thread.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(runner.create_one, range(2)))
        runner.selection(rows)
        runner.wait_ready(rows)
        runner.wave(rows, full=True)
        for row, kind in zip(sorted(rows, key=lambda x:x["index"]), ("PROCESS_RESTART", "DISCONNECT")):
            runner.restart_replay(row, kind)
        REPORT["state"] = "DIAGNOSTIC_PILOT_RUNNING"
        pilot = time.monotonic()
        REPORT["pilot_started_at_utc"] = now()
        emit()
        wave_count = 0
        while time.monotonic() - pilot < PILOT_SECONDS:
            if time.monotonic() - start > 1350:
                raise RuntimeError("DIAGNOSTIC_HARD_DEADLINE")
            runner.require_connection(rows)
            runner.wave(rows)
            wave_count += 1
            REPORT["completed_waves"] = wave_count
            REPORT["pilot_elapsed_seconds"] = round(time.monotonic()-pilot, 3)
            emit()
            time.sleep(min(60, max(0, PILOT_SECONDS-(time.monotonic()-pilot))))
        REPORT["pilot_elapsed_seconds"] = round(time.monotonic()-pilot, 3)
        REPORT["state"] = "BOUNDED_PILOT_COMPLETED_NO_REPRODUCTION"
    except BaseException as exc:
        terminal = runner_module.error_code(exc)
        REPORT["state"] = "FAIL"
        REPORT["error_code"] = terminal
        REPORT["exception_class"] = type(exc).__name__
    finally:
        if runner:
            preserve_agent_diagnostics(runner)
            try:
                runner.cleanup_rows([r for r in runner.rows if not r.get("cleaned")])
                REPORT["cleanup_state"] = "PASS"
                REPORT["cleaned_fixtures"] = runner.audit.get("cleaned_fixture_count", 0)
            except Exception as exc:
                REPORT["cleanup_state"] = "FAIL"
                REPORT["cleanup_error_code"] = runner_module.error_code(exc)
        TAIL_META["exit_before_stop"] = tail.poll() if tail else None
        stop_tail(tail)
        if tail_thread:
            tail_thread.join(timeout=3)
        REPORT["finished_at_utc"] = now()
        REPORT["elapsed_seconds"] = round(time.monotonic()-start, 3)
        REPORT["cause"] = "UNKNOWN_UNLESS_CORRELATED_SAFE_EXCEPTION_FOUND"
        emit()
        print(json.dumps({"state": REPORT["state"], "error_code": terminal, "cleanup_state": REPORT.get("cleanup_state"), "evidence": str(DEST)}), flush=True)
    return 1 if terminal or REPORT.get("cleanup_state") != "PASS" else 0

if __name__ == "__main__":
    def stop_signal(_number, _frame):
        raise RuntimeError("OWNED_DIAGNOSTIC_STOP_REQUESTED")
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    raise SystemExit(main())
