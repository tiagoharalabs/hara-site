INSERT OR REPLACE INTO tenants (
  tenant_id, display_name, state, environment, created_at_utc
) VALUES (
  'HARA-TENANT-DEMO-0001',
  'HARA Labs',
  'ACTIVE',
  'DEV',
  '2026-09-21T15:30:00Z'
);

INSERT OR REPLACE INTO users (
  subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role, created_at_utc
) VALUES (
  'HARA-SUBJECT-DEMO-0001',
  'HARA-TENANT-DEMO-0001',
  'https://auth.dev.haralabs.invalid/',
  'demo-user-0001',
  'demo@haralabs.invalid',
  'Conta HARA',
  'ACTIVE',
  'OWNER',
  '2026-09-21T15:30:00Z'
);

INSERT OR REPLACE INTO plans (
  plan_code, display_name, meter_id, period_kind, unit_limit, state
) VALUES
  ('TRIAL', 'Trial', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 1000, 'ACTIVE'),
  ('STANDARD', 'Standard', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 10000, 'ACTIVE'),
  ('SCALE', 'Scale', 'HARA_COMMANDER_GOVERNED_INVOKE', 'NONE', NULL, 'ACTIVE');

INSERT OR REPLACE INTO entitlements (
  entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc
) VALUES (
  'HARA-ENTITLEMENT-DEMO-0001',
  'HARA-TENANT-DEMO-0001',
  NULL,
  'STANDARD',
  'ACTIVE',
  '2026-09-01T00:00:00Z',
  NULL
);

INSERT OR REPLACE INTO billing_connections (
  billing_connection_id, tenant_id, provider, external_customer_id, external_subscription_id, state, created_at_utc, updated_at_utc
) VALUES (
  'HARA-BILLING-DEMO-0001',
  'HARA-TENANT-DEMO-0001',
  'DEV_MOCK',
  NULL,
  NULL,
  'NOT_CONNECTED',
  '2026-09-21T15:30:00Z',
  '2026-09-21T15:30:00Z'
);

INSERT OR REPLACE INTO tenants (
  tenant_id, display_name, state, environment, created_at_utc
) VALUES (
  'HARA-TENANT-QUOTA-0001',
  'Quota Validation Tenant',
  'ACTIVE',
  'DEV',
  '2026-09-21T15:30:00Z'
);

INSERT OR REPLACE INTO plans (
  plan_code, display_name, meter_id, period_kind, unit_limit, state
) VALUES (
  'DEV_ONE_UNIT',
  'DEV One Unit',
  'HARA_COMMANDER_GOVERNED_INVOKE',
  'CALENDAR_MONTH',
  1,
  'ACTIVE'
);

INSERT OR REPLACE INTO entitlements (
  entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc
) VALUES (
  'HARA-ENTITLEMENT-QUOTA-0001',
  'HARA-TENANT-QUOTA-0001',
  NULL,
  'DEV_ONE_UNIT',
  'ACTIVE',
  '2026-09-01T00:00:00Z',
  NULL
);


INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
SELECT plan_code, grant_code, '2026-09-22T14:20:00Z'
FROM (
  SELECT 'TRIAL' AS plan_code, 'COMMANDER_DISCOVERY' AS grant_code
  UNION ALL SELECT 'TRIAL', 'COMMANDER_READ_ONLY_INVOKE'
  UNION ALL SELECT 'TRIAL', 'COMMANDER_RECEIPT_READ'
  UNION ALL SELECT 'STANDARD', 'COMMANDER_DISCOVERY'
  UNION ALL SELECT 'STANDARD', 'COMMANDER_READ_ONLY_INVOKE'
  UNION ALL SELECT 'STANDARD', 'COMMANDER_RECEIPT_READ'
  UNION ALL SELECT 'SCALE', 'COMMANDER_DISCOVERY'
  UNION ALL SELECT 'SCALE', 'COMMANDER_READ_ONLY_INVOKE'
  UNION ALL SELECT 'SCALE', 'COMMANDER_RECEIPT_READ'
  UNION ALL SELECT 'DEV_ONE_UNIT', 'COMMANDER_DISCOVERY'
  UNION ALL SELECT 'DEV_ONE_UNIT', 'COMMANDER_READ_ONLY_INVOKE'
  UNION ALL SELECT 'DEV_ONE_UNIT', 'COMMANDER_RECEIPT_READ'
);


INSERT OR IGNORE INTO identity_bindings (
  identity_binding_id,
  subject_id,
  provider_code,
  issuer,
  external_subject,
  state,
  created_at_utc,
  revoked_at_utc
)
SELECT
  'PRIMARY:' || subject_id,
  subject_id,
  'PRIMARY_OIDC',
  oidc_issuer,
  oidc_subject,
  'ACTIVE',
  created_at_utc,
  NULL
FROM users;
