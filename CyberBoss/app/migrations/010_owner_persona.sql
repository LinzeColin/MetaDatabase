-- PANEL-2：主人设定的说话语气。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 为什么不放 service_state：那张表的 value_redacted_json 是**明文**列，
-- redactedJson 因此只允许枚举、布尔和 SAFE_TOKEN 形状的字符串。主人写的
-- 「怎么称呼我」和「还想让它注意什么」是自由文本，一进那张表就是把人写的东西
-- 明文落盘。所以单开一行，走和 inbox/outbox 载荷同一套 AES-256-GCM 信封。
--
-- 单行表：id 恒为 1。全机一份语气，不按用户分——R19 是一个共享 Bot，说话方式
-- 是这个 Bot 的属性，由主人定。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS owner_persona (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload_ciphertext BLOB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  8,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'PANEL-2',
  '__MIGRATION_008_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
