-- CB-800 / AC-029: durable receipts for scoped export and deletion.
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- Deletion is irreversible and may be interrupted at any step, so the proof
-- that a step ran has to outlive the process that ran it. These receipts are
-- the local idempotency ledger; the durable business record of the deletion is
-- the Private-Database tombstone written by step 07 of the frozen plan.

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS deletion_requests (
  request_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
  requested_at TEXT NOT NULL,
  completed_at TEXT,
  last_error_class TEXT
);

CREATE TABLE IF NOT EXISTS deletion_receipts (
  idempotency_key TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('succeeded','failed')),
  result_sha256 TEXT NOT NULL,
  irreversible INTEGER NOT NULL DEFAULT 0 CHECK(irreversible IN (0,1)),
  occurred_at TEXT NOT NULL,
  UNIQUE(request_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_deletion_receipts_user
  ON deletion_receipts(user_id, request_id);

CREATE TABLE IF NOT EXISTS export_receipts (
  export_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  object_ref TEXT,
  record_count INTEGER NOT NULL DEFAULT 0,
  generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_export_receipts_user
  ON export_receipts(user_id, generated_at);

-- A deletion receipt must never be edited after the fact: an audit trail that
-- can be rewritten is not an audit trail. Rows are insert-only.
CREATE TRIGGER IF NOT EXISTS trg_deletion_receipts_immutable
BEFORE UPDATE ON deletion_receipts
BEGIN
  SELECT RAISE(ABORT, 'deletion_receipt_immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_deletion_receipts_no_delete
BEFORE DELETE ON deletion_receipts
BEGIN
  SELECT RAISE(ABORT, 'deletion_receipt_immutable');
END;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  7,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-800',
  '__MIGRATION_007_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
