-- Source only. Apply/admit separately; default-OFF code never queries this table.
CREATE TABLE recovery_delivery_outbox (
  event_id TEXT NOT NULL,
  binding_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('PENDING','INFLIGHT','RETRY','DELIVERED','EXHAUSTED')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 8),
  next_attempt_ms INTEGER NOT NULL DEFAULT 0,
  lease_until_ms INTEGER NOT NULL DEFAULT 0,
  receipt_ref TEXT,
  receipt_sha256 TEXT,
  PRIMARY KEY(event_id,binding_id),
  FOREIGN KEY(event_id) REFERENCES commander_device_recovery_events(event_id) ON DELETE CASCADE,
  FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);
CREATE INDEX idx_recovery_delivery_due ON recovery_delivery_outbox(binding_id,state,next_attempt_ms);
