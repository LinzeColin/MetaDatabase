PRAGMA foreign_keys = ON;

-- Owner-only QR authorization lifecycle for the one shared CyberBoss iLink bot.
CREATE TABLE IF NOT EXISTS owner_wechat_activation_sessions (
  session_id TEXT PRIMARY KEY,
  qr_id TEXT NOT NULL UNIQUE,
  qr_content TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('wait','scanned','confirmed','expired','failed')),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  last_polled_at INTEGER,
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
  consumed_at INTEGER,
  error_code TEXT
);
CREATE INDEX IF NOT EXISTS ix_owner_wechat_activation_active
  ON owner_wechat_activation_sessions(status, expires_at) WHERE consumed_at IS NULL;

-- Public users do not log in on the website. They enter the same shared WeChat bot,
-- then receive user-scoped one-time setup links from WeChat when needed.
CREATE TABLE IF NOT EXISTS public_web_sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_hash TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  last_seen_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_public_web_sessions_user_active
  ON public_web_sessions(user_id, expires_at) WHERE revoked_at IS NULL;

-- Exactly one shared Bot account. Ordinary users are senders, not Bot-account owners.
CREATE TABLE IF NOT EXISTS weixin_accounts (
  singleton_key TEXT PRIMARY KEY CHECK(singleton_key = 'shared'),
  account_id TEXT NOT NULL UNIQUE,
  owner_user_id TEXT NOT NULL REFERENCES users(user_id),
  weixin_user_id TEXT NOT NULL,
  base_url TEXT NOT NULL,
  token_ciphertext TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','reauth_required','revoked','deleted')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_weixin_accounts_status ON weixin_accounts(status, updated_at);

CREATE TABLE IF NOT EXISTS weixin_sync_cursors (
  account_id TEXT PRIMARY KEY REFERENCES weixin_accounts(account_id),
  cursor TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS weixin_inbox_v8 (
  inbox_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES weixin_accounts(account_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  provider_message_id TEXT NOT NULL,
  payload_ciphertext TEXT NOT NULL,
  context_token_ciphertext TEXT,
  state TEXT NOT NULL CHECK(state IN ('received','accepted','rejected','processed','failed')),
  received_at INTEGER NOT NULL,
  processed_at INTEGER,
  error_code TEXT,
  UNIQUE(account_id, provider_message_id)
);
CREATE INDEX IF NOT EXISTS ix_weixin_inbox_v8_ready ON weixin_inbox_v8(state, received_at, inbox_id);
CREATE TABLE IF NOT EXISTS weixin_reply_outbox_v8 (
  outbox_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  account_id TEXT NOT NULL REFERENCES weixin_accounts(account_id),
  destination_hash TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  body_ciphertext TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('pending','claimed','confirmed','terminal_failed','delivery_unknown','cancelled')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
  next_attempt_at INTEGER NOT NULL,
  claimed_at INTEGER,
  confirmed_at INTEGER,
  provider_client_id TEXT,
  provider_receipt TEXT,
  error_code TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_weixin_reply_outbox_v8_dispatch
  ON weixin_reply_outbox_v8(state, next_attempt_at, created_at, outbox_id);
