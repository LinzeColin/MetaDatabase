-- CB-610 v0.0.0.8 additive multi-user foundation.
--
-- Numeric prefix 006 was materialized from the exact target inventory
-- (highest existing prefix 5); no fixed prefix is hard-coded anywhere.
-- Table definitions are the frozen taskpack template
-- (starter_kit/migrations/multiuser_foundation.sql.template,
-- sha256 49ab8cc87233de11f0bc9a21c15754b21509089a732f9139fb903e72470ea63e)
-- wrapped in this repository's existing migration transaction convention and
-- extended with the legacy user-scope backfill columns and valid-user guards.

PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK(role IN ('owner','user')),
  status TEXT NOT NULL CHECK(status IN ('pending_consent','active','suspended','deleting','deleted')),
  consent_version TEXT,
  consented_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_channels (
  channel TEXT NOT NULL,
  bot_account_ref TEXT NOT NULL,
  principal_hash TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  principal_ciphertext TEXT,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  PRIMARY KEY(channel, bot_account_ref, principal_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_channels_active_user
  ON user_channels(channel, user_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS invite_codes (
  code_hash TEXT PRIMARY KEY,
  max_uses INTEGER NOT NULL CHECK(max_uses >= 1),
  used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count >= 0),
  expires_at INTEGER,
  disabled_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
  user_id TEXT PRIMARY KEY REFERENCES users(user_id),
  provider_id TEXT,
  model_id TEXT,
  locale TEXT NOT NULL DEFAULT 'zh-CN',
  timezone TEXT,
  checkin_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setup_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  purpose TEXT NOT NULL CHECK(purpose IN ('provider','import','profile','privacy')),
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS web_sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_hash TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data_keys (
  user_id TEXT PRIMARY KEY REFERENCES users(user_id),
  key_version INTEGER NOT NULL,
  wrapped_key_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','rotating','destroyed')),
  created_at TEXT NOT NULL,
  rotated_at TEXT,
  destroyed_at TEXT
);

CREATE TABLE IF NOT EXISTS provider_credentials (
  user_id TEXT NOT NULL REFERENCES users(user_id),
  provider_id TEXT NOT NULL CHECK(provider_id IN ('openai','google','deepseek','anthropic')),
  key_version INTEGER NOT NULL,
  ciphertext_json TEXT NOT NULL,
  last4 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','invalid','revoked','deleted')),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, provider_id)
);

CREATE TABLE IF NOT EXISTS imports (
  import_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  source TEXT NOT NULL CHECK(source IN ('chatgpt','gemini','deepseek','claude')),
  source_hash TEXT NOT NULL,
  object_ref TEXT NOT NULL,
  state TEXT NOT NULL,
  compatibility TEXT NOT NULL,
  checkpoint_json TEXT,
  imported_records INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, source, source_hash)
);

CREATE TABLE IF NOT EXISTS profile_facts (
  fact_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  kind TEXT NOT NULL CHECK(kind IN ('explicit','inferred')),
  category TEXT NOT NULL,
  fact_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  source_ref TEXT,
  evidence_ref TEXT,
  confidence REAL,
  counterevidence_json TEXT NOT NULL DEFAULT '[]',
  decision TEXT NOT NULL CHECK(decision IN ('proposed','accepted','modified','rejected','deleted')),
  frozen INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, category, fact_key, version)
);

CREATE TABLE IF NOT EXISTS profile_decisions (
  decision_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  category TEXT NOT NULL,
  fact_key TEXT NOT NULL,
  decision TEXT NOT NULL,
  applies_to_future INTEGER NOT NULL DEFAULT 0,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_daily (
  user_id TEXT NOT NULL REFERENCES users(user_id),
  day TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, day)
);

CREATE TABLE IF NOT EXISTS consent_events (
  event_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  policy_version TEXT NOT NULL,
  scope TEXT NOT NULL,
  decision TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deletion_tombstones (
  tombstone_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  object_hash TEXT,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_budget_settings (
  user_id TEXT PRIMARY KEY REFERENCES users(user_id),
  daily_token_limit INTEGER NOT NULL CHECK(daily_token_limit > 0),
  monthly_token_limit INTEGER NOT NULL CHECK(monthly_token_limit > 0),
  per_request_reserved_token_limit INTEGER NOT NULL CHECK(per_request_reserved_token_limit > 0),
  per_request_output_token_limit INTEGER NOT NULL CHECK(per_request_output_token_limit > 0),
  soft_warning_ratio REAL NOT NULL CHECK(soft_warning_ratio > 0 AND soft_warning_ratio < 1),
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_token_usage_daily (
  user_id TEXT NOT NULL REFERENCES users(user_id),
  provider_id TEXT NOT NULL CHECK(provider_id IN ('openai','google','deepseek','anthropic','codex')),
  day TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0 CHECK(calls >= 0),
  input_tokens INTEGER NOT NULL DEFAULT 0 CHECK(input_tokens >= 0),
  output_tokens INTEGER NOT NULL DEFAULT 0 CHECK(output_tokens >= 0),
  total_tokens INTEGER NOT NULL DEFAULT 0 CHECK(total_tokens >= 0),
  fallback_usage_records INTEGER NOT NULL DEFAULT 0 CHECK(fallback_usage_records >= 0),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, provider_id, day)
);

CREATE TABLE IF NOT EXISTS model_budget_reservations (
  reservation_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  provider_id TEXT NOT NULL CHECK(provider_id IN ('openai','google','deepseek','anthropic','codex')),
  reserved_tokens INTEGER NOT NULL CHECK(reserved_tokens > 0),
  state TEXT NOT NULL CHECK(state IN ('reserved','settled','released','expired_charged')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  charged_tokens INTEGER CHECK(charged_tokens IS NULL OR charged_tokens >= 0),
  input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
  output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
  usage_reported INTEGER CHECK(usage_reported IS NULL OR usage_reported IN (0,1)),
  charge_mode TEXT CHECK(charge_mode IS NULL OR charge_mode IN ('actual','reserved','reservation_fallback')),
  reason_code TEXT,
  settled_at TEXT,
  UNIQUE(user_id, request_id)
);

CREATE INDEX IF NOT EXISTS ix_model_budget_reservations_active
  ON model_budget_reservations(user_id, provider_id, state, expires_at);

CREATE TABLE IF NOT EXISTS provider_circuits (
  circuit_key TEXT PRIMARY KEY,
  scope TEXT NOT NULL CHECK(scope IN ('global','user_provider')),
  user_id TEXT REFERENCES users(user_id),
  provider_id TEXT NOT NULL CHECK(provider_id IN ('openai','google','deepseek','anthropic','codex')),
  state TEXT NOT NULL CHECK(state IN ('closed','open','half_open')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK(consecutive_failures >= 0),
  last_code TEXT,
  opened_at INTEGER,
  retry_at INTEGER,
  probe_in_flight INTEGER NOT NULL DEFAULT 0 CHECK(probe_in_flight IN (0,1)),
  updated_at TEXT NOT NULL
);

-- Legacy runtime-spool rows predate multi-user scope. The column is added here;
-- the Owner backfill runs once inside the adapter before the guards below can
-- reject anything, so no accepted Stage 0-5 row is lost or rewritten.
ALTER TABLE inbox_messages ADD COLUMN user_id TEXT;
ALTER TABLE jobs ADD COLUMN user_id TEXT;
ALTER TABLE outbox_messages ADD COLUMN user_id TEXT;

-- Canonical sync carries both system-scope events (release, incident, recovery)
-- and, from CB-800, user-scope facts. NULL therefore means system scope; a
-- non-NULL value must reference a real user.
ALTER TABLE sync_spool ADD COLUMN user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_inbox_messages_user_id
  ON inbox_messages(user_id, received_at, id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id
  ON jobs(user_id, status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_outbox_messages_user_id
  ON outbox_messages(user_id, status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_sync_spool_user_id
  ON sync_spool(user_id, status, created_at, event_id);

CREATE TRIGGER IF NOT EXISTS trg_inbox_messages_valid_user_insert
BEFORE INSERT ON inbox_messages
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_inbox_messages_valid_user_update
BEFORE UPDATE OF user_id ON inbox_messages
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_jobs_valid_user_insert
BEFORE INSERT ON jobs
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_jobs_valid_user_update
BEFORE UPDATE OF user_id ON jobs
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_outbox_messages_valid_user_insert
BEFORE INSERT ON outbox_messages
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_outbox_messages_valid_user_update
BEFORE UPDATE OF user_id ON outbox_messages
WHEN NEW.user_id IS NULL
  OR NEW.user_id = ''
  OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_sync_spool_valid_user_insert
BEFORE INSERT ON sync_spool
WHEN NEW.user_id IS NOT NULL
  AND (
    NEW.user_id = ''
    OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
  )
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

CREATE TRIGGER IF NOT EXISTS trg_sync_spool_valid_user_update
BEFORE UPDATE OF user_id ON sync_spool
WHEN NEW.user_id IS NOT NULL
  AND (
    NEW.user_id = ''
    OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)
  )
BEGIN
  SELECT RAISE(ABORT, 'valid_user_id_required');
END;

-- A user row may never be deleted while scoped rows still reference it; user
-- removal goes through the CB-810 deletion plan (crypto-shred plus tombstone).
CREATE TRIGGER IF NOT EXISTS trg_users_scoped_rows_delete_guard
BEFORE DELETE ON users
WHEN EXISTS (SELECT 1 FROM inbox_messages WHERE user_id = OLD.user_id)
  OR EXISTS (SELECT 1 FROM jobs WHERE user_id = OLD.user_id)
  OR EXISTS (SELECT 1 FROM outbox_messages WHERE user_id = OLD.user_id)
BEGIN
  SELECT RAISE(ABORT, 'user_has_scoped_rows');
END;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  6,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-610',
  '__MIGRATION_006_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
