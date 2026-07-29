-- 机器人自己先开口的那些消息。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 主动打招呼、到点的提醒、入门引导——这三类都不经过 outbox（outbox 的每一行都
-- 要挂在一个 job 上，而它们没有 job），所以它们发出去之后在数据库里一个字都不
-- 留。后台「对话」栏因此看不到它们：主人能看见别人发来的每一句和它答的每一句，
-- 唯独看不见它自己主动说的那些。这张表补上那一段。
--
-- 正文和收件人一起加密进 payload_ciphertext（和 inbox/outbox 同一套信封）。
-- 收件人是微信号，属于真实 PII，不单独明文存一列。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS bot_initiated_messages (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('checkin','reminder','onboarding','system')),
  payload_ciphertext BLOB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0, 1)),
  error_class TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_bot_initiated_recent
  ON bot_initiated_messages(created_at DESC, id);

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  10,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'PANEL-6',
  '__MIGRATION_010_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
