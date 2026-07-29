PRAGMA foreign_keys = ON;
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
  locale TEXT NOT NULL DEFAULT 'zh-CN',
  timezone TEXT,
  checkin_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  purpose TEXT NOT NULL CHECK(purpose IN ('usage','import','profile','privacy')),
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

-- R18 Owner-approved shared DeepSeek runtime: exactly five ordinary seats,
-- no per-user daily/monthly quota, no global monthly quota, and one UTC daily 1B total-token gate.
CREATE TABLE IF NOT EXISTS ordinary_user_seats (
  user_id TEXT PRIMARY KEY REFERENCES users(user_id),
  seat_number INTEGER CHECK(seat_number BETWEEN 1 AND 5),
  state TEXT NOT NULL CHECK(state IN ('active','revoked')),
  claimed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ordinary_active_seat_number
  ON ordinary_user_seats(seat_number) WHERE state='active';

CREATE TABLE IF NOT EXISTS shared_token_daily (
  day_utc TEXT PRIMARY KEY,
  calls INTEGER NOT NULL DEFAULT 0,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
  cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0 CHECK(total_tokens BETWEEN 0 AND 1000000000),
  fallback_charges INTEGER NOT NULL DEFAULT 0,
  estimated_cost_nanocny INTEGER NOT NULL DEFAULT 0,
  reservation_overrun_tokens INTEGER NOT NULL DEFAULT 0,
  accounting_integrity_violations INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shared_token_reservations (
  reservation_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  day_utc TEXT NOT NULL,
  reserved_tokens INTEGER NOT NULL CHECK(reserved_tokens >= 0),
  state TEXT NOT NULL CHECK(state IN ('reserved','settled','released','expired_charged')),
  charged_tokens INTEGER,
  created_at_ms INTEGER NOT NULL,
  expires_at_ms INTEGER NOT NULL,
  settled_at_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_shared_reservations_active
  ON shared_token_reservations(day_utc,state,expires_at_ms);

CREATE TABLE IF NOT EXISTS shared_provider_circuit (
  circuit_key TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK(state IN ('closed','open','half_open')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  retry_at_ms INTEGER NOT NULL DEFAULT 0,
  probe_in_flight INTEGER NOT NULL DEFAULT 0 CHECK(probe_in_flight IN (0,1)),
  probe_expires_at_ms INTEGER NOT NULL DEFAULT 0,
  last_code TEXT,
  updated_at TEXT NOT NULL
);
