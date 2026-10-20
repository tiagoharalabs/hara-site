// The count and insertion execute in one SQLite write statement. D1 batch()
// then consumes the pairing token in the same transaction only after insert.
export const DEVICE_ENROLL_INSERT_SQL = `INSERT INTO commander_devices
  (device_id, pairing_id, tenant_id, enrolled_by_subject_id, device_name, platform,
   architecture, agent_version, tunnel_mode, credential_hash, state,
   created_at_utc, last_seen_at_utc, revoked_at_utc, approval_mode)
 SELECT ?, p.pairing_id, p.tenant_id, p.subject_id, ?, ?, ?, ?, 'OUTBOUND_RELAY', ?,
        'ACTIVE', ?, ?, NULL, ?
   FROM device_pairing_tokens p
  WHERE p.token_hash = ?
    AND p.consumed_at_utc IS NULL
    AND p.superseded_at_utc IS NULL
    AND p.expires_at_utc > ?
    AND EXISTS (
      SELECT 1 FROM entitlements e
      JOIN plans pl ON pl.plan_code = e.plan_code
     WHERE e.tenant_id = p.tenant_id
       AND e.state = 'ACTIVE'
       AND e.valid_from_utc <= ?
       AND (e.valid_until_utc IS NULL OR e.valid_until_utc > ?)
       AND pl.state = 'ACTIVE'
       AND (pl.active_device_limit IS NULL OR (
         SELECT COUNT(*) FROM commander_devices d
          WHERE d.tenant_id = p.tenant_id
            AND d.state = 'ACTIVE' AND d.revoked_at_utc IS NULL
       ) < pl.active_device_limit)
    )`;

export const DEVICE_ENROLL_CONSUME_SQL = `UPDATE device_pairing_tokens
    SET consumed_at_utc = ?
  WHERE token_hash = ?
    AND consumed_at_utc IS NULL
    AND superseded_at_utc IS NULL
    AND expires_at_utc > ?
    AND EXISTS (
      SELECT 1 FROM commander_devices d
       WHERE d.pairing_id = device_pairing_tokens.pairing_id
         AND d.device_id = ?
    )`;

export const DEVICE_ENROLL_LIMIT_SQL = `SELECT 1 AS at_limit
  FROM device_pairing_tokens p
 WHERE p.token_hash = ?
   AND p.consumed_at_utc IS NULL
   AND p.superseded_at_utc IS NULL
   AND p.expires_at_utc > ?
   AND EXISTS (
     SELECT 1 FROM entitlements e
     JOIN plans pl ON pl.plan_code = e.plan_code
    WHERE e.tenant_id = p.tenant_id
      AND e.state = 'ACTIVE'
      AND e.valid_from_utc <= ?
      AND (e.valid_until_utc IS NULL OR e.valid_until_utc > ?)
      AND pl.state = 'ACTIVE'
      AND pl.active_device_limit IS NOT NULL
      AND (
        SELECT COUNT(*) FROM commander_devices d
         WHERE d.tenant_id = p.tenant_id
           AND d.state = 'ACTIVE' AND d.revoked_at_utc IS NULL
      ) >= pl.active_device_limit
   )
 LIMIT 1`;
