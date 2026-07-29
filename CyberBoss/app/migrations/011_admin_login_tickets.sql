-- LOGIN-2：微信发「后台」换来的一次性登录票。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 为什么不复用 setup_tokens：那张表的 purpose 上有 CHECK 约束，只收
-- provider/import/profile/privacy 四种，而且它的语义是"某个用户的某项设置"。
-- 后台登录是"服务器管理者"这一件完全不同的事，混进去等于让一张用户设置票
-- 有机会换到后台。单开一张表，边界就在类型上，不在判断里。
--
-- 票只存哈希。即使这张表被人看到，也换不出可用的链接。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS admin_login_tickets (
  token_hash TEXT PRIMARY KEY,
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_admin_login_tickets_expiry
  ON admin_login_tickets(expires_at) WHERE used_at IS NULL;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  9,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'LOGIN-2',
  '__MIGRATION_009_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
