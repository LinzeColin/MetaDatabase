PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

ALTER TABLE sync_spool ADD COLUMN batch_id TEXT;
ALTER TABLE sync_spool ADD COLUMN batch_event_set_sha256 TEXT;
ALTER TABLE sync_spool ADD COLUMN manifest_record_sha256 TEXT;
ALTER TABLE sync_spool ADD COLUMN remote_object_path TEXT;
ALTER TABLE sync_spool ADD COLUMN verified_at TEXT;
ALTER TABLE sync_spool ADD COLUMN retry_after_ms INTEGER;
ALTER TABLE sync_spool ADD COLUMN last_receipt_sha256 TEXT;

CREATE INDEX idx_sync_batch
ON sync_spool(batch_id, status, next_attempt_at, created_at, event_id);

CREATE TRIGGER sync_spool_identity_immutable_guard
BEFORE UPDATE ON sync_spool
WHEN NEW.id IS NOT OLD.id
  OR NEW.event_id IS NOT OLD.event_id
  OR NEW.object_type IS NOT OLD.object_type
  OR NEW.object_id IS NOT OLD.object_id
  OR NEW.canonical_path IS NOT OLD.canonical_path
  OR NEW.payload_redacted_json IS NOT OLD.payload_redacted_json
  OR NEW.payload_sha256 IS NOT OLD.payload_sha256
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_sync_event');
END;

CREATE TRIGGER sync_spool_delete_guard
BEFORE DELETE ON sync_spool
BEGIN
  SELECT RAISE(ABORT, 'immutable_sync_event');
END;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  5,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-240',
  '__MIGRATION_005_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
