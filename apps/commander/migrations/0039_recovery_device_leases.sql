-- Additive DEV qualification for #163. No PROD migration is authorized.
CREATE TABLE recovery_device_leases (
 device_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 lease_token TEXT NOT NULL,
 lease_until_ms INTEGER NOT NULL,
 FOREIGN KEY(device_id) REFERENCES commander_devices(device_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);
