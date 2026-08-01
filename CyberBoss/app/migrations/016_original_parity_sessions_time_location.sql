-- v0.0.0.9 原版语义：会话、时间、位置、回执。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 这一版要修的是「持续 Agent 的核心语义被稀释」。四张表分别兜住四件事：
--
--   agent_sessions_v009       —— 主人和每个 Companion 各自的**同一条**会话。
--     在此之前 Companion 完全无状态：runUserModelTurn 只传了微信的
--     contextToken，一句上下文都没有，所以「第二轮记得第一轮」实现上不成立。
--     PRIMARY KEY (user_id, mode) 保证一个人一个模式只有一条；
--     UNIQUE (session_key) 保证两个人不会撞进同一条会话。
--
--   user_location_profiles_v009 —— 时区和**粗粒度**位置。
--     没有 latitude / longitude / raw_ip 这三列，是设计上的硬门（AC-013）：
--     不存在的列不会泄漏。要更精确的定位就得先改表，改表会被评审看见。
--     confidence + confirmed 分开：推断出来的和用户亲口确认的不能混为一谈。
--
--   parity_receipts_v009      —— 真实链路回执。
--     user_scope_hash / session_key_hash 存的是哈希不是原值——回执要进 Status
--     和公开页，原值进去就是 AC-043 说的泄漏。
--     real_path_verified 是这一版 Status 不许「配置性伪绿」的那把锁：
--     没有真实链路成功过，就不能显示健康。
--
--   时间列一律成对：*_at_utc 是瞬时，*_at_beijing 是权威表达（AC-010）。
--     只存一个的话，跨服务排序和给用户看的时间必然有一个是错的。
--
-- 来源：任务包 v0.0.0.9 Starter Kit
-- migrations/next_original_parity_sessions_time_location.sql，按本仓编号约定
-- 物化为 016（对应 MIGRATIONS 里的 version 14）。

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS agent_sessions_v009 (
  user_id TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('OWNER','COMPANION')),
  session_key TEXT NOT NULL,
  runtime_kind TEXT NOT NULL,
  runtime_ref_ciphertext BLOB,
  runtime_ref_hash TEXT,
  state TEXT NOT NULL CHECK (state IN ('active','paused','reconcile','closed')) DEFAULT 'active',
  context_version INTEGER NOT NULL DEFAULT 1,
  last_event_at_utc TEXT,
  last_event_at_beijing TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  PRIMARY KEY (user_id, mode),
  UNIQUE (session_key)
);

CREATE TABLE IF NOT EXISTS user_location_profiles_v009 (
  user_id TEXT PRIMARY KEY,
  timezone TEXT NOT NULL,
  coarse_city TEXT,
  coarse_country TEXT,
  source TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  confirmed INTEGER NOT NULL CHECK (confirmed IN (0,1)) DEFAULT 0,
  consent_scope TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parity_receipts_v009 (
  receipt_id TEXT PRIMARY KEY,
  capability_id TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('OWNER','COMPANION','SYSTEM')),
  user_scope_hash TEXT,
  session_key_hash TEXT,
  real_path_verified INTEGER NOT NULL CHECK (real_path_verified IN (0,1)),
  outcome TEXT NOT NULL CHECK (outcome IN ('success','failure','unknown')),
  occurred_at_utc TEXT NOT NULL,
  occurred_at_beijing TEXT NOT NULL,
  artifact_digest TEXT,
  public_detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_parity_receipts_cap_time_v009
  ON parity_receipts_v009(capability_id, occurred_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_state_v009
  ON agent_sessions_v009(state, updated_at_utc);

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  14,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB9-140',
  '__MIGRATION_014_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
