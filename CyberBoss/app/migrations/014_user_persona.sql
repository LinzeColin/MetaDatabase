-- 每个人自己的语气。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 迁移 010 的注释里写着「全机一份语气，不按用户分——R19 是一个共享 Bot，说话
-- 方式是这个 Bot 的属性」。那句话在当时是对的：那时候只有主人一个人在用。
--
-- 现在每个人扫码绑自己的微信、各有各的号，「同一个 Bot 对所有人一个腔调」就
-- 不成立了。主人那一行现在的意思变成**默认值**：没给自己设过语气的人沿用它，
-- 设过的人用自己这一行。
--
-- 只存「怎么说话」那几项（tone / length / emoji / callMe / note）。
-- proactive（主动打招呼）和 access（名额、入口）仍然只属于主人——前者的目标
-- 只能是主人，后者是整台机器的开门规则，都不是某个人的属性。
--
-- 键是 user_id，和记忆、时间线、日记同一个隔离边界；不是 senderId。
-- senderId 是「某个号里的某个微信」，同一个人换个号就变了。
--
-- 载荷和 owner_persona 同一套 AES-256-GCM 信封，AAD 是
-- user_persona:{user_id}:payload。不放 service_state：那张表的
-- value_redacted_json 是明文列，而「怎么称呼我」是人写的自由文本。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS user_persona (
  user_id TEXT PRIMARY KEY,
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
  12,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'PERSONA-1',
  '__MIGRATION_012_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
