PRAGMA foreign_keys = ON;

-- Better Auth 1.6.25 core schema. Column names remain compatible with the default models.
CREATE TABLE IF NOT EXISTS "user" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "name" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "emailVerified" INTEGER NOT NULL DEFAULT 0 CHECK ("emailVerified" IN (0,1)),
  "image" TEXT,
  "createdAt" INTEGER NOT NULL,
  "updatedAt" INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS "user_email_unique" ON "user"("email");

CREATE TABLE IF NOT EXISTS "session" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "userId" TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "token" TEXT NOT NULL,
  "expiresAt" INTEGER NOT NULL,
  "ipAddress" TEXT,
  "userAgent" TEXT,
  "createdAt" INTEGER NOT NULL,
  "updatedAt" INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS "session_token_unique" ON "session"("token");
CREATE INDEX IF NOT EXISTS "session_user_idx" ON "session"("userId");
CREATE INDEX IF NOT EXISTS "session_expiry_idx" ON "session"("expiresAt");

CREATE TABLE IF NOT EXISTS "account" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "userId" TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "accountId" TEXT NOT NULL,
  "providerId" TEXT NOT NULL,
  "accessToken" TEXT,
  "refreshToken" TEXT,
  "accessTokenExpiresAt" INTEGER,
  "refreshTokenExpiresAt" INTEGER,
  "scope" TEXT,
  "idToken" TEXT,
  "password" TEXT,
  "createdAt" INTEGER NOT NULL,
  "updatedAt" INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS "account_provider_unique" ON "account"("providerId", "accountId");
CREATE INDEX IF NOT EXISTS "account_user_idx" ON "account"("userId");

CREATE TABLE IF NOT EXISTS "verification" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "identifier" TEXT NOT NULL,
  "value" TEXT NOT NULL,
  "expiresAt" INTEGER NOT NULL,
  "createdAt" INTEGER NOT NULL,
  "updatedAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "verification_identifier_idx" ON "verification"("identifier");
CREATE INDEX IF NOT EXISTS "verification_expiry_idx" ON "verification"("expiresAt");

CREATE TABLE IF NOT EXISTS "rateLimit" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "key" TEXT NOT NULL UNIQUE,
  "count" INTEGER NOT NULL,
  "lastRequest" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "rateLimit_last_request_idx" ON "rateLimit"("lastRequest");

CREATE TABLE IF NOT EXISTS profile_settings (
  user_id TEXT PRIMARY KEY REFERENCES "user"("id") ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  timezone TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'zh-CN',
  show_welcome INTEGER NOT NULL DEFAULT 1 CHECK (show_welcome IN (0,1)),
  privacy_policy_version TEXT,
  privacy_consent_state TEXT NOT NULL DEFAULT 'not_requested' CHECK (privacy_consent_state IN ('not_requested','accepted','revoked')),
  privacy_consented_at INTEGER,
  privacy_revoked_at INTEGER,
  data_version INTEGER NOT NULL DEFAULT 1,
  sync_token TEXT,
  sync_token_expires_at INTEGER,
  last_synced_at INTEGER,
  deletion_state TEXT NOT NULL DEFAULT 'active' CHECK (deletion_state IN ('active','pending')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK ((sync_token IS NULL AND sync_token_expires_at IS NULL) OR (sync_token IS NOT NULL AND sync_token_expires_at IS NOT NULL)),
  CHECK (
    (privacy_consent_state = 'not_requested' AND privacy_consented_at IS NULL AND privacy_revoked_at IS NULL)
    OR (privacy_consent_state = 'accepted' AND privacy_policy_version IS NOT NULL AND privacy_consented_at IS NOT NULL AND privacy_revoked_at IS NULL)
    OR (privacy_consent_state = 'revoked' AND privacy_policy_version IS NOT NULL AND privacy_consented_at IS NOT NULL AND privacy_revoked_at IS NOT NULL AND privacy_revoked_at >= privacy_consented_at)
  )
);

CREATE TABLE IF NOT EXISTS privacy_consent_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  policy_version TEXT NOT NULL CHECK (length(policy_version) BETWEEN 1 AND 80),
  notice_sha256 TEXT NOT NULL CHECK (length(notice_sha256)=64),
  decision TEXT NOT NULL CHECK (decision IN ('accepted','revoked')),
  decided_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS privacy_consent_events_user_time_idx ON privacy_consent_events(user_id, decided_at);
CREATE INDEX IF NOT EXISTS profile_settings_sync_idx ON profile_settings(sync_token_expires_at);

CREATE TABLE IF NOT EXISTS habit_definitions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
  icon_key TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, id)
);
CREATE INDEX IF NOT EXISTS habit_definitions_user_idx ON habit_definitions(user_id, sort_order);

CREATE TABLE IF NOT EXISTS habit_checkins (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  habit_id TEXT NOT NULL,
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  checked_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, habit_id, local_date),
  FOREIGN KEY(user_id, habit_id) REFERENCES habit_definitions(user_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS habit_checkins_user_date_idx ON habit_checkins(user_id, local_date);

CREATE TABLE IF NOT EXISTS todos (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 5000),
  due_date TEXT,
  priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high')),
  completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
  completed_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS todos_user_state_idx ON todos(user_id, completed, due_date);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('expense','income')),
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (length(currency)=3),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 40),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_user_date_idx ON ledger_entries(user_id, local_date);
CREATE INDEX IF NOT EXISTS ledger_user_kind_idx ON ledger_entries(user_id, kind, local_date);

CREATE TABLE IF NOT EXISTS file_objects (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  object_key TEXT NOT NULL UNIQUE,
  module TEXT NOT NULL CHECK (module IN ('food','diary','profile','other')),
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL CHECK (byte_size BETWEEN 1 AND 10485760),
  sha256 TEXT NOT NULL CHECK (length(sha256)=64),
  width INTEGER,
  height INTEGER,
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','pending_delete')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK (substr(object_key, 1, length('users/' || user_id || '/')) = 'users/' || user_id || '/')
);
CREATE UNIQUE INDEX IF NOT EXISTS file_objects_user_id_unique ON file_objects(user_id, id);
CREATE INDEX IF NOT EXISTS file_objects_user_idx ON file_objects(user_id, module, created_at);

CREATE TABLE IF NOT EXISTS food_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  food_name TEXT NOT NULL CHECK (length(food_name) BETWEEN 1 AND 200),
  calories INTEGER NOT NULL CHECK (calories BETWEEN 0 AND 20000),
  meal TEXT NOT NULL CHECK (meal IN ('breakfast','lunch','dinner','snack')),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  photo_object_id TEXT REFERENCES file_objects(id) ON DELETE SET NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS food_user_date_idx ON food_entries(user_id, local_date, meal);

CREATE TABLE IF NOT EXISTS exercise_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  activity TEXT NOT NULL CHECK (length(activity) BETWEEN 1 AND 120),
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 1440),
  calories_burned INTEGER CHECK (calories_burned BETWEEN 0 AND 20000),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS exercise_user_date_idx ON exercise_entries(user_id, local_date);

CREATE TABLE IF NOT EXISTS weight_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  weight_grams INTEGER NOT NULL CHECK (weight_grams BETWEEN 10000 AND 500000),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, local_date)
);
CREATE INDEX IF NOT EXISTS weight_user_date_idx ON weight_entries(user_id, local_date);

CREATE TABLE IF NOT EXISTS schedule_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 5000),
  starts_at INTEGER NOT NULL,
  ends_at INTEGER,
  all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0,1)),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK (ends_at IS NULL OR ends_at >= starts_at)
);
CREATE INDEX IF NOT EXISTS schedule_user_time_idx ON schedule_events(user_id, starts_at);

CREATE TABLE IF NOT EXISTS anniversaries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  repeat_yearly INTEGER NOT NULL DEFAULT 1 CHECK (repeat_yearly IN (0,1)),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS anniversaries_user_date_idx ON anniversaries(user_id, local_date);

CREATE TABLE IF NOT EXISTS diary_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  mood TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '' CHECK (length(title) <= 200),
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 30000),
  photo_object_id TEXT REFERENCES file_objects(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS diary_user_date_idx ON diary_entries(user_id, local_date);

CREATE TABLE IF NOT EXISTS savings_goals (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
  target_cents INTEGER NOT NULL CHECK (target_cents > 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (length(currency)=3),
  target_date TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, id)
);
CREATE INDEX IF NOT EXISTS savings_goals_user_idx ON savings_goals(user_id, archived);

CREATE TABLE IF NOT EXISTS savings_transactions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  goal_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents != 0),
  local_date TEXT NOT NULL CHECK (length(local_date)=10),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(user_id, goal_id) REFERENCES savings_goals(user_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS savings_transactions_user_goal_idx ON savings_transactions(user_id, goal_id, local_date);

CREATE TABLE IF NOT EXISTS period_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  start_date TEXT NOT NULL CHECK (length(start_date)=10),
  end_date TEXT NOT NULL CHECK (length(end_date)=10),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK (end_date >= start_date),
  UNIQUE(user_id, start_date, end_date)
);
CREATE INDEX IF NOT EXISTS period_user_start_idx ON period_entries(user_id, start_date);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  row_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  endpoint TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_code INTEGER,
  response_digest TEXT,
  state TEXT NOT NULL CHECK (state IN ('started','completed','failed')),
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, endpoint, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idempotency_expiry_idx ON idempotency_keys(expires_at);

CREATE TABLE IF NOT EXISTS legacy_imports (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  source_instance_id TEXT NOT NULL,
  source_schema_version INTEGER NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
  state TEXT NOT NULL CHECK (state IN ('previewed','applying','completed','failed')),
  item_counts_json TEXT NOT NULL,
  error_code TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, source_instance_id, payload_sha256)
);
CREATE INDEX IF NOT EXISTS legacy_imports_user_idx ON legacy_imports(user_id, created_at);

CREATE TABLE IF NOT EXISTS outbox_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending','processing','completed','failed')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at INTEGER NOT NULL,
  lease_expires_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS outbox_due_idx ON outbox_events(state, next_attempt_at);

CREATE TABLE IF NOT EXISTS security_audit_events (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES "user"("id") ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  outcome TEXT NOT NULL,
  ip_digest TEXT,
  user_agent_digest TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS security_audit_time_idx ON security_audit_events(created_at);


CREATE TRIGGER IF NOT EXISTS food_photo_tenant_insert
BEFORE INSERT ON food_entries
WHEN NEW.photo_object_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM file_objects
  WHERE id = NEW.photo_object_id AND user_id = NEW.user_id AND module = 'food' AND state = 'active'
)
BEGIN
  SELECT RAISE(ABORT, 'food_photo_tenant_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS food_photo_tenant_update
BEFORE UPDATE OF user_id, photo_object_id ON food_entries
WHEN NEW.photo_object_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM file_objects
  WHERE id = NEW.photo_object_id AND user_id = NEW.user_id AND module = 'food' AND state = 'active'
)
BEGIN
  SELECT RAISE(ABORT, 'food_photo_tenant_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS diary_photo_tenant_insert
BEFORE INSERT ON diary_entries
WHEN NEW.photo_object_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM file_objects
  WHERE id = NEW.photo_object_id AND user_id = NEW.user_id AND module = 'diary' AND state = 'active'
)
BEGIN
  SELECT RAISE(ABORT, 'diary_photo_tenant_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS diary_photo_tenant_update
BEFORE UPDATE OF user_id, photo_object_id ON diary_entries
WHEN NEW.photo_object_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM file_objects
  WHERE id = NEW.photo_object_id AND user_id = NEW.user_id AND module = 'diary' AND state = 'active'
)
BEGIN
  SELECT RAISE(ABORT, 'diary_photo_tenant_mismatch');
END;
