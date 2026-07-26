PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

ALTER TABLE outbox_messages ADD COLUMN logical_message_sha256 TEXT;
ALTER TABLE outbox_messages ADD COLUMN provider_client_id TEXT;
ALTER TABLE outbox_messages ADD COLUMN claim_owner TEXT;
ALTER TABLE outbox_messages ADD COLUMN claim_expires_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN dispatch_started_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN last_attempt_at TEXT;
ALTER TABLE outbox_messages ADD COLUMN confirmation_state TEXT NOT NULL
  DEFAULT 'unconfirmed'
  CHECK (confirmation_state IN ('unconfirmed', 'confirmed', 'ambiguous'));
ALTER TABLE outbox_messages ADD COLUMN dispatch_outcome TEXT NOT NULL
  DEFAULT 'not_started'
  CHECK (
    dispatch_outcome IN (
      'not_started',
      'known_failure',
      'confirmed',
      'ambiguous'
    )
  );
ALTER TABLE outbox_messages ADD COLUMN recovery_class TEXT;

CREATE UNIQUE INDEX idx_outbox_provider_client_id
ON outbox_messages(provider_client_id)
WHERE provider_client_id IS NOT NULL;

CREATE INDEX idx_outbox_claim
ON outbox_messages(status, claim_expires_at, next_attempt_at, created_at, id);

CREATE TABLE outbox_attempt_events (
  id TEXT PRIMARY KEY,
  outbox_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
  event_type TEXT NOT NULL CHECK (
    event_type IN (
      'started',
      'retry_scheduled',
      'confirmed',
      'failed_terminal',
      'ambiguous'
    )
  ),
  error_class TEXT,
  retry_at TEXT,
  provider_receipt_hash TEXT,
  occurred_at TEXT NOT NULL,
  UNIQUE (outbox_id, attempt_number, event_type),
  FOREIGN KEY (outbox_id) REFERENCES outbox_messages(id) ON DELETE RESTRICT
);

CREATE INDEX idx_outbox_attempt_events_row
ON outbox_attempt_events(outbox_id, attempt_number, occurred_at, id);

CREATE TRIGGER outbox_attempt_events_immutable_update_guard
BEFORE UPDATE ON outbox_attempt_events
BEGIN
  SELECT RAISE(ABORT, 'immutable_outbox_attempt_event');
END;

CREATE TRIGGER outbox_attempt_events_immutable_delete_guard
BEFORE DELETE ON outbox_attempt_events
BEGIN
  SELECT RAISE(ABORT, 'immutable_outbox_attempt_event');
END;

CREATE TRIGGER outbox_sending_claim_guard
BEFORE UPDATE ON outbox_messages
WHEN NEW.status = 'sending'
  AND (
    NEW.claim_owner IS NULL
    OR NEW.claim_expires_at IS NULL
    OR NEW.provider_client_id IS NULL
    OR NEW.logical_message_sha256 IS NULL
  )
BEGIN
  SELECT RAISE(ABORT, 'outbox_sending_claim_required');
END;

CREATE TRIGGER outbox_confirmation_truth_guard
BEFORE UPDATE ON outbox_messages
WHEN NEW.status = 'confirmed'
  AND (
    NEW.confirmation_state <> 'confirmed'
    OR NEW.dispatch_outcome <> 'confirmed'
    OR NEW.confirmed_at IS NULL
    OR NEW.provider_receipt_hash IS NULL
    OR NEW.dispatch_started_at IS NULL
  )
BEGIN
  SELECT RAISE(ABORT, 'outbox_confirmation_required');
END;

CREATE TRIGGER outbox_confirmed_immutable_guard
BEFORE UPDATE ON outbox_messages
WHEN OLD.status = 'confirmed'
  AND (
    NEW.status IS NOT OLD.status
    OR NEW.confirmation_state IS NOT OLD.confirmation_state
    OR NEW.dispatch_outcome IS NOT OLD.dispatch_outcome
    OR NEW.confirmed_at IS NOT OLD.confirmed_at
    OR NEW.provider_receipt_hash IS NOT OLD.provider_receipt_hash
    OR NEW.provider_client_id IS NOT OLD.provider_client_id
    OR NEW.payload_sha256 IS NOT OLD.payload_sha256
    OR NEW.dedupe_key IS NOT OLD.dedupe_key
  )
BEGIN
  SELECT RAISE(ABORT, 'confirmed_outbox_immutable');
END;

CREATE TRIGGER outbox_retry_known_outcome_guard
BEFORE UPDATE ON outbox_messages
WHEN NEW.status = 'retry'
  AND OLD.status <> 'confirmed'
  AND OLD.dispatch_started_at IS NOT NULL
  AND NEW.dispatch_outcome <> 'known_failure'
BEGIN
  SELECT RAISE(ABORT, 'outbox_retry_requires_known_failure');
END;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  4,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-230',
  '__MIGRATION_004_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
