PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  source_commit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inbox_messages (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_account_hash TEXT NOT NULL,
  source_message_id TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  user_ref_hash TEXT NOT NULL,
  message_type TEXT NOT NULL CHECK (message_type IN ('text','command','unsupported')),
  payload_ciphertext BLOB,
  payload_sha256 TEXT NOT NULL,
  context_token_ciphertext BLOB,
  cursor_batch_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('accepted','rejected','consumed')),
  reject_reason TEXT,
  received_at TEXT NOT NULL,
  durable_at TEXT NOT NULL,
  consumed_at TEXT,
  UNIQUE (source, source_account_hash, source_message_id),
  UNIQUE (correlation_id)
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  correlation_id TEXT NOT NULL UNIQUE,
  inbox_id TEXT NOT NULL,
  workspace_alias TEXT NOT NULL,
  runtime TEXT NOT NULL CHECK (runtime IN ('codex','claude')),
  operation_class TEXT NOT NULL CHECK (operation_class IN ('read_only','bounded_mutation','command')),
  status TEXT NOT NULL CHECK (status IN (
    'received','queued','running','waiting_approval','failed_retryable','succeeded',
    'failed_terminal','cancelled','expired','reply_pending','replied','reply_failed',
    'canonical_pending','canonical_synced','rejected'
  )),
  state_version INTEGER NOT NULL DEFAULT 1,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 1,
  lease_owner TEXT,
  lease_expires_at TEXT,
  input_sha256 TEXT NOT NULL,
  output_sha256 TEXT,
  summary_redacted TEXT,
  error_class TEXT,
  error_redacted TEXT,
  created_at TEXT NOT NULL,
  queued_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL,
  canonical_state TEXT NOT NULL DEFAULT 'pending' CHECK (canonical_state IN ('pending','sync_pending','synced','integrity_error')),
  canonical_object_sha256 TEXT,
  FOREIGN KEY (inbox_id) REFERENCES inbox_messages(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical ON jobs(canonical_state, updated_at);

CREATE TABLE IF NOT EXISTS job_events (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  payload_redacted_json TEXT NOT NULL DEFAULT '{}',
  payload_sha256 TEXT,
  occurred_at TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  canonical_state TEXT NOT NULL DEFAULT 'pending' CHECK (canonical_state IN ('pending','sync_pending','synced','integrity_error')),
  canonical_object_sha256 TEXT,
  FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_time ON job_events(job_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_job_events_canonical ON job_events(canonical_state, recorded_at);

CREATE TABLE IF NOT EXISTS outbox_messages (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('weixin')),
  target_ref_ciphertext BLOB,
  dedupe_key TEXT NOT NULL UNIQUE,
  message_kind TEXT NOT NULL CHECK (message_kind IN ('accepted','progress','result','error','cancelled')),
  chunk_index INTEGER NOT NULL DEFAULT 1,
  chunk_count INTEGER NOT NULL DEFAULT 1,
  payload_ciphertext BLOB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','sending','retry','confirmed','failed_terminal')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_at TEXT,
  last_error_class TEXT,
  last_error_redacted TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  confirmed_at TEXT,
  provider_receipt_hash TEXT,
  FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox_messages(status, next_attempt_at, created_at);

CREATE TABLE IF NOT EXISTS sync_spool (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  payload_redacted_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','syncing','retry','synced','integrity_error')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error_class TEXT,
  last_error_redacted TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  synced_at TEXT,
  canonical_object_sha256 TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_due ON sync_spool(status, next_attempt_at, created_at);

CREATE TABLE IF NOT EXISTS service_state (
  key TEXT PRIMARY KEY,
  value_redacted_json TEXT NOT NULL,
  value_sha256 TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS singleton_leases (
  name TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  boot_id TEXT,
  pid INTEGER,
  acquired_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations(version, applied_at, source_commit)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'taskpack-v0.0.0.4');

COMMIT;
PRAGMA integrity_check;
