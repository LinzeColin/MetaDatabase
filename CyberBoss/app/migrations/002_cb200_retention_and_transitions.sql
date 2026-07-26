PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

ALTER TABLE schema_migrations ADD COLUMN checksum_sha256 TEXT;

ALTER TABLE inbox_messages ADD COLUMN payload_expires_at TEXT;
ALTER TABLE inbox_messages ADD COLUMN payload_redacted_at TEXT;
ALTER TABLE inbox_messages ADD COLUMN context_expires_at TEXT;
ALTER TABLE inbox_messages ADD COLUMN context_redacted_at TEXT;

ALTER TABLE outbox_messages ADD COLUMN payload_expires_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN payload_redacted_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN target_ref_expires_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN target_ref_redacted_at TEXT;

CREATE TABLE job_state_transitions (
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  PRIMARY KEY (from_status, to_status)
) WITHOUT ROWID;

INSERT INTO job_state_transitions(from_status, to_status) VALUES
  ('received', 'queued'),
  ('received', 'rejected'),
  ('queued', 'running'),
  ('queued', 'expired'),
  ('running', 'waiting_approval'),
  ('running', 'succeeded'),
  ('running', 'failed_retryable'),
  ('running', 'cancelled'),
  ('running', 'failed_terminal'),
  ('waiting_approval', 'running'),
  ('waiting_approval', 'cancelled'),
  ('failed_retryable', 'queued'),
  ('failed_retryable', 'failed_terminal'),
  ('succeeded', 'reply_pending'),
  ('failed_terminal', 'reply_pending'),
  ('cancelled', 'reply_pending'),
  ('reply_pending', 'replied'),
  ('reply_pending', 'reply_failed'),
  ('replied', 'canonical_pending'),
  ('reply_failed', 'canonical_pending'),
  ('canonical_pending', 'canonical_synced');

CREATE TRIGGER jobs_status_transition_guard
BEFORE UPDATE OF status ON jobs
WHEN NEW.status <> OLD.status
  AND NOT EXISTS (
    SELECT 1
    FROM job_state_transitions
    WHERE from_status = OLD.status AND to_status = NEW.status
  )
BEGIN
  SELECT RAISE(ABORT, 'illegal_job_status_transition');
END;

CREATE TRIGGER job_events_immutable_update_guard
BEFORE UPDATE ON job_events
WHEN NEW.id IS NOT OLD.id
  OR NEW.job_id IS NOT OLD.job_id
  OR NEW.correlation_id IS NOT OLD.correlation_id
  OR NEW.event_type IS NOT OLD.event_type
  OR NEW.from_status IS NOT OLD.from_status
  OR NEW.to_status IS NOT OLD.to_status
  OR NEW.payload_redacted_json IS NOT OLD.payload_redacted_json
  OR NEW.payload_sha256 IS NOT OLD.payload_sha256
  OR NEW.occurred_at IS NOT OLD.occurred_at
  OR NEW.recorded_at IS NOT OLD.recorded_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_job_event');
END;

CREATE TRIGGER job_events_immutable_delete_guard
BEFORE DELETE ON job_events
BEGIN
  SELECT RAISE(ABORT, 'immutable_job_event');
END;

UPDATE schema_migrations
SET checksum_sha256 = '__MIGRATION_001_CHECKSUM__'
WHERE version = 1 AND checksum_sha256 IS NULL;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  2,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-200',
  '__MIGRATION_002_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
