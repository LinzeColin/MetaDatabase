PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
PRAGMA secure_delete = ON;

CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  email TEXT,
  display_name TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'zh-CN',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS account_keys (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  wrapped_dek TEXT NOT NULL,
  key_id TEXT NOT NULL,
  updated_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS credentials (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_subject TEXT NOT NULL,
  secret_hash TEXT,
  secret_encrypted TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(kind, provider, provider_subject)
) STRICT;
CREATE INDEX IF NOT EXISTS credentials_account_idx ON credentials(account_id);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  id TEXT,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  csrf_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL DEFAULT 0,
  expires_at INTEGER NOT NULL,
  recent_auth_at INTEGER NOT NULL,
  user_agent_hash TEXT,
  ip_prefix_hash TEXT
) STRICT;
CREATE UNIQUE INDEX IF NOT EXISTS sessions_public_id_idx ON sessions(id) WHERE id IS NOT NULL;
CREATE INDEX IF NOT EXISTS sessions_account_idx ON sessions(account_id, expires_at);

CREATE TABLE IF NOT EXISTS auth_throttle (
  bucket_key TEXT PRIMARY KEY,
  failures INTEGER NOT NULL,
  first_failure_at INTEGER NOT NULL,
  locked_until INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS auth_throttle_expiry_idx ON auth_throttle(updated_at);

CREATE TABLE IF NOT EXISTS oauth_transactions (
  state_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  intent TEXT NOT NULL,
  account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
  verifier_encrypted TEXT,
  redirect_uri TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS provider_connections (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_subject TEXT NOT NULL,
  access_token_encrypted TEXT NOT NULL,
  refresh_token_encrypted TEXT,
  scopes TEXT NOT NULL DEFAULT '',
  expires_at INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(account_id, provider),
  UNIQUE(provider, provider_subject)
) STRICT;

CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  object_key TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  word_count INTEGER NOT NULL DEFAULT 0,
  category TEXT,
  version INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER,
  UNIQUE(account_id, source, external_id)
) STRICT;
CREATE INDEX IF NOT EXISTS notes_account_updated_idx ON notes(account_id, updated_at, id);

CREATE TABLE IF NOT EXISTS note_objects (
  object_key TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  note_id TEXT NOT NULL,
  created_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS note_objects_account_idx ON note_objects(account_id);

CREATE TABLE IF NOT EXISTS sync_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  entity_version INTEGER NOT NULL,
  payload_hash TEXT NOT NULL,
  occurred_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS sync_events_account_seq_idx ON sync_events(account_id, seq);

CREATE TABLE IF NOT EXISTS consents (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  behavior_analytics INTEGER NOT NULL DEFAULT 0,
  recommendation_personalization INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS behavior_events (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  value_json TEXT NOT NULL,
  occurred_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS behavior_account_time_idx ON behavior_events(account_id, occurred_at);

CREATE TABLE IF NOT EXISTS import_jobs (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  state TEXT NOT NULL,
  selection_json TEXT NOT NULL DEFAULT '{}',
  selection_encrypted TEXT,
  progress_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT NOT NULL,
  error_code TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  worker_id TEXT,
  lease_until INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(account_id, idempotency_key)
) STRICT;
CREATE INDEX IF NOT EXISTS import_jobs_queue_idx ON import_jobs(state, lease_until, created_at);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker_id TEXT PRIMARY KEY,
  worker_type TEXT NOT NULL,
  version TEXT NOT NULL,
  heartbeat_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS weread_sync_state (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  summary_json TEXT NOT NULL DEFAULT '{}',
  last_sync_at INTEGER,
  updated_at INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS recommendations (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  reason TEXT NOT NULL,
  deep_link TEXT,
  score REAL NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS recommendations_account_idx ON recommendations(account_id, score DESC);

CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS outbox_state_idx ON outbox(state, available_at);

PRAGMA user_version = 18;
