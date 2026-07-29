-- 每一轮的执行轨迹：它开始想了、想了多久、烧了多少 token、调没调工具、为什么失败。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 在这之前，runtime 的事件只在内存里流过 runtimeAdapter.onEvent 就没了；库里
-- 只有状态流转（收下→排队→派发→完成），主人在后台看不到"它当时到底在干什么"。
-- 一轮回复慢了、失败了，唯一的线索是一个错误码。
--
-- 有一条要写明白：codex 只吐 turn started/completed/failed、reply delta/
-- completed、context updated（token 计数）、approval requested 这几种，**没有**
-- 单独的"推理内容"事件。所以这张表能给的是执行轨迹，不是模型的内心独白。
-- 别把它当成后者。
--
-- payload 和正文一起加密（和 inbox/outbox 同一套信封）：reply delta 里就是
-- 用户看到的那些字，属于真实聊天内容。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS turn_traces (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  thread_id TEXT,
  turn_id TEXT,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload_ciphertext BLOB,
  occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_turn_traces_turn
  ON turn_traces(turn_id, seq);
CREATE INDEX IF NOT EXISTS ix_turn_traces_recent
  ON turn_traces(occurred_at DESC, id);

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  11,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CONSOLE-1',
  '__MIGRATION_011_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
