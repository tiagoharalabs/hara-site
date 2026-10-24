#!/usr/bin/env python3
"""Offline integrity proof for Commander D1 migration 0011."""

from __future__ import annotations

import sqlite3
from pathlib import Path

COMMANDER = Path(__file__).resolve().parent.parent
MIGRATION = COMMANDER / "migrations" / "0011_event_v2_transport.sql"


BASE_SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE tenants (
  tenant_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUSPENDED','CLOSED')),
  environment TEXT NOT NULL CHECK (environment IN ('DEV','REVIEW','PRODUCTION')),
  created_at_utc TEXT NOT NULL
);

CREATE TABLE users (
  subject_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  oidc_issuer TEXT NOT NULL,
  oidc_subject TEXT NOT NULL,
  email TEXT,
  display_name TEXT,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUSPENDED','REVOKED')),
  role TEXT NOT NULL CHECK (role IN ('OWNER','ADMIN','MEMBER','REVIEWER')),
  created_at_utc TEXT NOT NULL,
  UNIQUE (oidc_issuer, oidc_subject)
);

CREATE TABLE device_pairing_tokens (
  pairing_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  consumed_at_utc TEXT,
  superseded_at_utc TEXT
);

CREATE TABLE commander_devices (
  device_id TEXT PRIMARY KEY,
  pairing_id TEXT NOT NULL UNIQUE REFERENCES device_pairing_tokens(pairing_id),
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  enrolled_by_subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('LINUX','WINDOWS')),
  architecture TEXT,
  agent_version TEXT,
  tunnel_mode TEXT NOT NULL DEFAULT 'OUTBOUND_RELAY'
    CHECK (tunnel_mode IN ('OUTBOUND_RELAY')),
  credential_hash TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','REVOKED')),
  created_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT,
  revoked_at_utc TEXT
);

CREATE INDEX idx_commander_devices_tenant
  ON commander_devices(tenant_id, state);
CREATE INDEX idx_commander_devices_subject
  ON commander_devices(enrolled_by_subject_id, state);
CREATE INDEX idx_commander_devices_last_seen
  ON commander_devices(last_seen_at_utc);

CREATE TABLE commander_device_calls (
  call_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  tool_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (
    state IN ('PENDING','EXECUTING','COMPLETED','FAILED','CANCELLED','EXPIRED')
  ),
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  claimed_at_utc TEXT,
  completed_at_utc TEXT,
  result_json TEXT,
  error_code TEXT
);
CREATE INDEX idx_device_calls_poll
  ON commander_device_calls(device_id, state, created_at_utc);
CREATE INDEX idx_device_calls_tenant
  ON commander_device_calls(tenant_id, state, created_at_utc);
CREATE INDEX idx_device_calls_expiry
  ON commander_device_calls(state, expires_at_utc);

CREATE TABLE commander_device_selections (
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  selected_at_utc TEXT NOT NULL,
  PRIMARY KEY (tenant_id, subject_id)
);
CREATE INDEX idx_device_selections_device
  ON commander_device_selections(device_id);

INSERT INTO tenants VALUES
  ('T1','Tenant','ACTIVE','DEV','2026-09-25T00:00:00.000Z');
INSERT INTO users VALUES
  ('S1','T1','https://issuer.example/','sub','u@example.invalid','User','ACTIVE','OWNER','2026-09-25T00:00:00.000Z');
INSERT INTO device_pairing_tokens VALUES
  ('P1','hash1','T1','S1','2026-09-25T00:00:00.000Z','2026-09-26T00:00:00.000Z','2026-09-25T00:01:00.000Z',NULL);
INSERT INTO commander_devices VALUES
  ('D1','P1','T1','S1','Device','LINUX','x86_64','0.3.7','OUTBOUND_RELAY','cred1','ACTIVE','2026-09-25T00:01:00.000Z','2026-09-25T00:02:00.000Z',NULL);
INSERT INTO commander_device_calls VALUES
  ('C1','R1','T1','S1','D1','hara.health','{}','COMPLETED','2026-09-25T00:02:00.000Z','2026-09-25T00:03:00.000Z','2026-09-25T00:02:10.000Z','2026-09-25T00:02:11.000Z','{}',NULL);
INSERT INTO commander_device_selections VALUES
  ('T1','S1','D1','2026-09-25T00:02:00.000Z');
"""


def fk_targets(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[2] for row in db.execute(f'PRAGMA foreign_key_list("{table}")')}


def main() -> int:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "PRAGMA defer_foreign_keys = ON" in sql
    assert "'OUTBOUND_RELAY','EVENT_V2','EVENT_V2_OFFLINE'" in sql
    assert sql.index("DROP TABLE commander_device_selections") < sql.index(
        "DROP TABLE commander_devices"
    )
    assert sql.index("DROP TABLE commander_device_calls") < sql.index(
        "DROP TABLE commander_devices"
    )

    db = sqlite3.connect(":memory:")
    db.executescript(BASE_SCHEMA)

    before = {
        "devices": db.execute("SELECT count(*) FROM commander_devices").fetchone()[0],
        "calls": db.execute("SELECT count(*) FROM commander_device_calls").fetchone()[0],
        "selections": db.execute("SELECT count(*) FROM commander_device_selections").fetchone()[0],
    }

    db.executescript(sql)

    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    after = {
        "devices": db.execute("SELECT count(*) FROM commander_devices").fetchone()[0],
        "calls": db.execute("SELECT count(*) FROM commander_device_calls").fetchone()[0],
        "selections": db.execute("SELECT count(*) FROM commander_device_selections").fetchone()[0],
    }
    assert after == before == {"devices": 1, "calls": 1, "selections": 1}

    assert fk_targets(db, "commander_device_calls") >= {"commander_devices"}
    assert fk_targets(db, "commander_device_selections") >= {"commander_devices"}

    db.execute(
        "UPDATE commander_devices SET tunnel_mode='EVENT_V2' WHERE device_id='D1'"
    )
    assert db.execute(
        "SELECT tunnel_mode FROM commander_devices WHERE device_id='D1'"
    ).fetchone()[0] == "EVENT_V2"

    db.execute(
        "UPDATE commander_devices SET tunnel_mode='EVENT_V2_OFFLINE' WHERE device_id='D1'"
    )
    assert db.execute(
        "SELECT tunnel_mode FROM commander_devices WHERE device_id='D1'"
    ).fetchone()[0] == "EVENT_V2_OFFLINE"

    try:
        db.execute(
            "UPDATE commander_devices SET tunnel_mode='ARBITRARY' WHERE device_id='D1'"
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("ARBITRARY_TUNNEL_MODE_NOT_DENIED")

    expected_indexes = {
        "idx_commander_devices_tenant",
        "idx_commander_devices_subject",
        "idx_commander_devices_last_seen",
        "idx_device_calls_poll",
        "idx_device_calls_tenant",
        "idx_device_calls_expiry",
        "idx_device_selections_device",
    }
    actual_indexes = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
        )
    }
    assert expected_indexes.issubset(actual_indexes)

    # Preserve ON DELETE behavior after the rebuild.
    db.execute("DELETE FROM commander_devices WHERE device_id='D1'")
    assert db.execute("SELECT count(*) FROM commander_device_calls").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM commander_device_selections").fetchone()[0] == 0

    print("COMMANDER_EVENT_V2_SCHEMA_0011=PASS")
    print("COMMANDER_EVENT_V2_SCHEMA_DATA_PRESERVED=PASS")
    print("COMMANDER_EVENT_V2_SCHEMA_FOREIGN_KEYS=PASS")
    print("COMMANDER_EVENT_V2_SCHEMA_INDEXES=PASS")
    print("COMMANDER_EVENT_V2_TUNNEL_MODES=V1_AND_V2_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
