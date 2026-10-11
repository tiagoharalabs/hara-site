#!/usr/bin/env python3
"""Metadata-only, bounded Event V2 telemetry. No command content or identifiers.

Writes are batched locally; a seven-day cumulative summary may be attached to
the existing infrequent Event V2 liveness frame. No independent HTTP upload.
"""
from __future__ import annotations

import os
import sqlite3
import stat
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA = "hara.commander-device-telemetry.v1"
METRICS = (
    "connections", "disconnects", "reconnects", "session_errors",
    "durable_calls", "transient_calls", "transient_failures",
    "liveness_attempts", "transport_pings", "connected_seconds",
)
WINDOW_DAYS = 7
PERSIST_INTERVAL_SECONDS = 5 * 60
MAX_COUNTER = 1_000_000_000
MAX_AMOUNT = 86400
TABLE = "event_v2_telemetry_daily"


def utc_day(value=None):
    at = value if value is not None else datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("EVENT_TELEMETRY_TIMEZONE_REQUIRED")
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d")


def require_private_regular_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("EVENT_TELEMETRY_UNSAFE_FILE")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("EVENT_TELEMETRY_UNSAFE_PERMISSIONS")


class LocalTelemetry:
    """Single-process aggregator; SQLite is the bounded persistence authority."""

    def __init__(self, path: Path, *, monotonic=time.monotonic):
        self.path = Path(path)
        self.monotonic = monotonic
        self.last_flush = monotonic()
        self.day = utc_day()
        self.pending = {metric: 0 for metric in METRICS}
        self._setup()

    def _connect(self):
        require_private_regular_file(self.path)
        conn = sqlite3.connect(str(self.path), timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=2000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _setup(self):
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS " + TABLE + " ("
                "day_utc TEXT PRIMARY KEY,"
                + ",".join(metric + " INTEGER NOT NULL DEFAULT 0" for metric in METRICS)
                + ")"
            )
            conn.execute("DELETE FROM " + TABLE + " WHERE day_utc < ?",
                         ((datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS-1)).isoformat(),))

    def add(self, metric: str, amount: int = 1, *, day: str | None = None):
        if metric not in METRICS or type(amount) is not int or not 0 <= amount <= MAX_AMOUNT:
            raise ValueError("EVENT_TELEMETRY_METRIC_INVALID")
        current_day = day or utc_day()
        if current_day != self.day:
            self.flush()
            self.day = current_day
        self.pending[metric] += amount
        if self.monotonic() - self.last_flush >= PERSIST_INTERVAL_SECONDS:
            self.flush()

    def flush(self):
        if not any(self.pending.values()):
            self.last_flush = self.monotonic()
            return
        values = [self.pending[key] for key in METRICS]
        # Even the largest attainable one-day counts are clamped safely.
        update = ",".join(
            key + "=MIN(" + str(MAX_COUNTER) + "," + TABLE + "." + key + "+excluded." + key + ")"
            for key in METRICS
        )
        sql = (
            "INSERT INTO " + TABLE + "(day_utc," + ",".join(METRICS) + ") VALUES("
            + ",".join("?" for _ in range(len(METRICS) + 1)) + ") "
            + "ON CONFLICT(day_utc) DO UPDATE SET " + update
        )
        with self._connect() as conn:
            conn.execute(sql, (self.day, *values))
            cutoff = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS-1)).isoformat()
            conn.execute("DELETE FROM " + TABLE + " WHERE day_utc < ?", (cutoff,))
        self.pending = {metric: 0 for metric in METRICS}
        self.last_flush = self.monotonic()

    def snapshot(self):
        # Flush first; a snapshot is never published based solely on volatile state.
        self.flush()
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=WINDOW_DAYS-1)).isoformat()
        columns = ",".join("COALESCE(SUM(" + k + "),0) AS " + k for k in METRICS)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT " + columns + " FROM " + TABLE + " WHERE day_utc >= ?", (cutoff,)
            ).fetchone()
        counters = {metric: min(MAX_COUNTER, int(row[metric])) for metric in METRICS}
        return {"schema": SCHEMA, "window_days": WINDOW_DAYS, **counters}

    def close(self):
        self.flush()
