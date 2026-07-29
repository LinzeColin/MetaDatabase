-- 待办和日程。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 主人的原话：「需要做到能和真正的ai一样，能陪伴，能处理待办，能当闹钟，能日历」。
-- 提醒（reminder-queue.json）解决的是「到点戳我一下」，那是一次性的、发完就没了；
-- 待办和日程是**留着的东西**——今天没做完的明天还在，下周的会现在就该看得到。
-- 所以它们进库，不进那个队列文件。
--
-- 一张表两种东西，靠 kind 分：
--   todo  —— 待办。due_at 可以为空（「有空去买菜」没有截止时间）。
--   event —— 日程。due_at 必填，那就是它开始的时刻。
--
-- 分两张表也行，但两边的读写、隔离、后台展示会长得一模一样，只是把同样的代码
-- 抄两遍。合成一张之后，后台那一栏一次查询就能把「他的待办和日程」一起列出来。
--
-- 标题和备注是人写的自由文本，一律进密文载荷（AES-256-GCM，AAD 是
-- user_item:{id}:payload）。留在明文列里的只有时间戳和状态码——它们要用来排序、
-- 筛「今天的」、判「做完没有」，而且本身不含任何内容。
--
-- 键是 user_id，和语气、记忆、时间线同一个隔离边界。AAD 里带 item id：把别人的
-- 密文换到这一行上，解密会直接失败，而不是悄悄串了人。

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS user_items (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_ciphertext BLOB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  -- 待办可以没有截止时间；日程一定有开始时刻。
  due_at TEXT,
  -- 做完了才有值。日程「做完」的意思是它已经过去或被主人划掉。
  done_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 「这个人现在还没做完的，按时间排」——待办栏和日程栏都是这一个查询。
CREATE INDEX IF NOT EXISTS idx_user_items_open
  ON user_items(user_id, kind, done_at, due_at);

-- 后台要按时间倒着看全部人的，不分人。
CREATE INDEX IF NOT EXISTS idx_user_items_recent
  ON user_items(created_at);

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  13,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'TODO-1',
  '__MIGRATION_013_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
