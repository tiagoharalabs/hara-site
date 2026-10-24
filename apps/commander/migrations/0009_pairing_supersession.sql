PRAGMA foreign_keys = ON;

ALTER TABLE device_pairing_tokens
  ADD COLUMN superseded_at_utc TEXT;

UPDATE device_pairing_tokens
   SET superseded_at_utc = created_at_utc
 WHERE consumed_at_utc IS NULL
   AND superseded_at_utc IS NULL
   AND EXISTS (
     SELECT 1
       FROM device_pairing_tokens newer
      WHERE newer.tenant_id = device_pairing_tokens.tenant_id
        AND newer.subject_id = device_pairing_tokens.subject_id
        AND newer.consumed_at_utc IS NULL
        AND newer.superseded_at_utc IS NULL
        AND (
          newer.created_at_utc > device_pairing_tokens.created_at_utc
          OR (
            newer.created_at_utc = device_pairing_tokens.created_at_utc
            AND newer.pairing_id > device_pairing_tokens.pairing_id
          )
        )
   );

CREATE UNIQUE INDEX IF NOT EXISTS idx_device_pairing_current_subject
  ON device_pairing_tokens(tenant_id, subject_id)
  WHERE consumed_at_utc IS NULL
    AND superseded_at_utc IS NULL;
