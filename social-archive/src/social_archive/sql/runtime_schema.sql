PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── 账号系统（v0.0.0.7 / T01）────────────────────────────────────────
--
-- 租户锚点是 source_account、user_relation 与 platform_collection 三张
-- **关系**表，不是 content。
--
-- 为什么 content 不带 user_id：content 是内容寻址的、全局去重的
-- （UNIQUE(platform, external_content_id)）。两个用户收藏同一条帖子时它只有一行，
-- 那么 user_id 只能记下"谁先到"，成为一个看着像隔离、实际谁都拦不住的列。
-- 真正的所有权边是 user_relation（"我收藏了它"），隔离必须建在那里。
-- 这也保住了 ARCHITECTURE.md 要求"保留不动"的内容寻址内核。

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  display_name TEXT,
  created_at TEXT NOT NULL,
  -- 本版本站点仍在 Cloudflare Access 后面，只有 Owner 一个用户；
  -- 但结构按多用户建，第二步只需要摘掉 Access。
  is_owner INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oauth_identity (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK(provider IN ('google','github')),
  subject TEXT NOT NULL,          -- provider 侧的稳定唯一 ID，不是邮箱
  created_at TEXT NOT NULL,
  UNIQUE(provider, subject)
);

CREATE TABLE IF NOT EXISTS session (
  id TEXT PRIMARY KEY,            -- 随机不可猜；Cookie 里只放这个，不用 JWT（撤销更简单）
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS extension_token (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,  -- 只存哈希；明文只在签发那一刻交给扩展
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS source_account (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  platform TEXT NOT NULL,
  external_account_id TEXT,
  display_name TEXT,
  auth_ref TEXT,
  connection_state TEXT NOT NULL DEFAULT 'disconnected',
  auth_method TEXT,
  auth_handle_ref TEXT,
  auto_sync_enabled INTEGER NOT NULL DEFAULT 1,
  sync_interval_minutes INTEGER NOT NULL DEFAULT 360,
  last_verified_at TEXT,
  last_sync_at TEXT,
  last_error_code TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(platform, external_account_id)
);

CREATE TABLE IF NOT EXISTS content (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  external_content_id TEXT,
  canonical_url TEXT NOT NULL,
  content_type TEXT NOT NULL DEFAULT 'unknown',
  title TEXT,
  author_name TEXT,
  published_at TEXT,
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  availability TEXT NOT NULL DEFAULT 'observed',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  summary TEXT,
  language TEXT,
  media_count INTEGER NOT NULL DEFAULT 0,
  last_synced_at TEXT,
  UNIQUE(platform, external_content_id),
  UNIQUE(platform, canonical_url)
);

-- 所有权边。租户隔离建在这张表上，不在 content 上。
-- 既有 UNIQUE(source_account_id, content_id, relation_type, collection_key) 已经
-- 隐含按用户收敛（一个 source_account 只属于一个 user），且比任务包给的
-- (user_id, platform, external_content_id, relation_type, collection_key) 更细
-- ——同一用户在同一平台连两个账号时不会被错误合并。故幂等键保持不变。
-- source_account_id 可为空（手动保存没有平台账号），所以 user_id 必须独立成列，
-- 不能只靠 join source_account 推导。
CREATE TABLE IF NOT EXISTS user_relation (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  source_account_id TEXT,
  content_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  collection_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  relation_observed_at TEXT,
  external_relation_id TEXT,
  source_order INTEGER,
  last_sync_run_id TEXT,
  missing_complete_scan_count INTEGER NOT NULL DEFAULT 0,
  closed_at TEXT,
  FOREIGN KEY(source_account_id) REFERENCES source_account(id),
  FOREIGN KEY(content_id) REFERENCES content(id),
  UNIQUE(source_account_id, content_id, relation_type, collection_key)
);

CREATE TABLE IF NOT EXISTS observation (
  id TEXT PRIMARY KEY,
  connector_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  FOREIGN KEY(content_id) REFERENCES content(id),
  UNIQUE(connector_id, payload_sha256)
);

CREATE TABLE IF NOT EXISTS scan_receipt (
  id TEXT PRIMARY KEY,
  connector_id TEXT NOT NULL,
  source_account_id TEXT,
  relation_type TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  completeness TEXT NOT NULL CHECK(completeness IN ('complete','partial','failed','unknown')),
  item_count INTEGER NOT NULL DEFAULT 0,
  cursor_start TEXT,
  cursor_end TEXT,
  failure_code TEXT,
  evidence_sha256 TEXT,
  FOREIGN KEY(source_account_id) REFERENCES source_account(id)
);

CREATE TABLE IF NOT EXISTS artifact (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL,
  archive_level TEXT NOT NULL CHECK(archive_level IN ('L0','L1','L2','L3')),
  artifact_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  media_type TEXT,
  local_path TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'staged',
  FOREIGN KEY(content_id) REFERENCES content(id),
  UNIQUE(content_id, artifact_type, sha256)
);

CREATE TABLE IF NOT EXISTS object_replica (
  id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  object_key TEXT NOT NULL,
  status TEXT NOT NULL,
  etag TEXT,
  verified_sha256 TEXT,
  original_sha256 TEXT,
  encryption TEXT,
  updated_at TEXT NOT NULL,
  last_error_code TEXT,
  FOREIGN KEY(artifact_id) REFERENCES artifact(id),
  UNIQUE(artifact_id, store_id)
);

CREATE TABLE IF NOT EXISTS job (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  connector_id TEXT,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  not_before TEXT NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error_code TEXT,
  last_error_message TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  not_before TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  last_error_code TEXT,
  UNIQUE(event_type, aggregate_id, payload_sha256)
);

CREATE TABLE IF NOT EXISTS connector_state (
  connector_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK(state IN ('healthy','degraded','paused','disabled','blocked_environment')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  consecutive_successes INTEGER NOT NULL DEFAULT 0,
  circuit_open_until TEXT,
  policy_gate TEXT NOT NULL DEFAULT 'unknown',
  auth_gate TEXT NOT NULL DEFAULT 'unknown',
  technical_gate TEXT NOT NULL DEFAULT 'unknown',
  last_success_at TEXT,
  last_failure_at TEXT,
  last_error_code TEXT,
  last_checked_at TEXT,
  latency_ms INTEGER,
  last_message_zh TEXT,
  updated_at TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS destination_state (
  destination_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK(state IN ('connected','needs_user_action','checking','degraded','expired','blocked_policy','disabled')),
  enabled INTEGER NOT NULL DEFAULT 0,
  last_success_at TEXT,
  last_failure_at TEXT,
  last_error_code TEXT,
  last_checked_at TEXT,
  latency_ms INTEGER,
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  last_message_zh TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS destination_binding (
  id TEXT PRIMARY KEY,
  destination_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  remote_id TEXT,
  remote_path TEXT,
  projection_sha256 TEXT NOT NULL,
  last_export_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(content_id) REFERENCES content(id),
  UNIQUE(destination_id, content_id)
);

CREATE TABLE IF NOT EXISTS destination_receipt (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  destination_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('done','noop','failed')),
  projection_sha256 TEXT NOT NULL,
  remote_id TEXT,
  remote_path TEXT,
  attempted_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  error_code TEXT,
  message_zh TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(content_id) REFERENCES content(id)
);

-- Worker 心跳（v0.0.0.18）。
--
-- 2026-08-06 一次被打断的部署留下的状态是：core-api 起来了、**core-worker 卡在
-- Created 没启动**。而 /health 由 api 提供，它照样回 ok——**从外面完全看不出
-- 后台没在跑**，任务只会静静积压。这正是这个产品一直在防的那个形状：
-- 健康检查不读出问题的那半边。
--
-- 一行就够：worker 每轮循环写一次时间戳，/health 拿它和现在比。
CREATE TABLE IF NOT EXISTS worker_heartbeat (
  worker_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quota_state (
  store_id TEXT PRIMARY KEY,
  measured_bytes INTEGER NOT NULL DEFAULT 0,
  soft_limit_bytes INTEGER NOT NULL,
  hard_limit_bytes INTEGER NOT NULL,
  action TEXT NOT NULL DEFAULT 'allow',
  measured_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
  content_id UNINDEXED,
  title,
  author_name,
  body,
  tags,
  tokenize='unicode61'
);

CREATE INDEX IF NOT EXISTS idx_job_claim ON job(status, not_before, lease_expires_at);
-- 「这条内容的视频有没有被平台挡下来」——资料库那一列要按它现算。
-- 部分表达式索引：只索引真正失败的那些 L3 任务，表再大也只有几十行。
CREATE INDEX IF NOT EXISTS idx_job_l3_failed_content
    ON job(json_extract(payload_json, '$.content_id'))
    WHERE job_type = 'download_l3' AND status = 'failed';
CREATE INDEX IF NOT EXISTS idx_outbox_delivery ON outbox(status, not_before);
CREATE INDEX IF NOT EXISTS idx_relation_content ON user_relation(content_id, status);
CREATE INDEX IF NOT EXISTS idx_artifact_sha ON artifact(sha256);
CREATE INDEX IF NOT EXISTS idx_replica_status ON object_replica(store_id, status);
CREATE INDEX IF NOT EXISTS idx_destination_binding_content ON destination_binding(content_id, destination_id);
CREATE INDEX IF NOT EXISTS idx_destination_receipt_lookup ON destination_receipt(destination_id, content_id, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_destination_receipt_status ON destination_receipt(status, finished_at DESC);

-- v0.0.0.6 account-mirror state is rebuildable Runtime Journal data. It stores
-- cursors, queues and observed relation IDs, never browser cookies or headers.
CREATE TABLE IF NOT EXISTS platform_collection (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  source_account_id TEXT NOT NULL,
  external_collection_id TEXT,
  relation_type TEXT NOT NULL,
  name TEXT NOT NULL,
  item_count INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(source_account_id) REFERENCES source_account(id),
  UNIQUE(source_account_id, relation_type, external_collection_id)
);

CREATE TABLE IF NOT EXISTS sync_run (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  source_account_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode IN ('first_full','incremental','manual_repair','official_import','browser_import')),
  trigger_type TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL CHECK(status IN ('queued','authorizing','discovering','scanning','normalizing','artifacting','exporting','completed','partial','paused','cancelled','failed','blocked_environment')),
  relation_scope_json TEXT NOT NULL DEFAULT '[]',
  discovered_count INTEGER NOT NULL DEFAULT 0,
  imported_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  unavailable_count INTEGER NOT NULL DEFAULT 0,
  cursor_json TEXT NOT NULL DEFAULT '{}',
  resume_token TEXT,
  completeness TEXT NOT NULL DEFAULT 'unknown' CHECK(completeness IN ('complete','partial','failed','unknown')),
  started_at TEXT,
  updated_at TEXT NOT NULL,
  completed_at TEXT,
  last_error_code TEXT,
  last_error_message TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(source_account_id) REFERENCES source_account(id)
);

CREATE TABLE IF NOT EXISTS sync_run_event (
  id TEXT PRIMARY KEY,
  sync_run_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(sync_run_id) REFERENCES sync_run(id),
  UNIQUE(sync_run_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS sync_checkpoint (
  id TEXT PRIMARY KEY,
  source_account_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  collection_key TEXT NOT NULL DEFAULT '',
  cursor_json TEXT NOT NULL DEFAULT '{}',
  known_anchor TEXT,
  last_complete_sync_run_id TEXT,
  last_success_at TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(source_account_id) REFERENCES source_account(id),
  UNIQUE(source_account_id, relation_type, collection_key)
);

CREATE TABLE IF NOT EXISTS sync_seen_relation (
  sync_run_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  collection_key TEXT NOT NULL DEFAULT '',
  relation_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  PRIMARY KEY(sync_run_id, relation_type, collection_key, relation_id),
  FOREIGN KEY(sync_run_id) REFERENCES sync_run(id)
);

CREATE TABLE IF NOT EXISTS sync_run_scope (
  sync_run_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  collection_key TEXT NOT NULL DEFAULT '__relation__',
  status TEXT NOT NULL DEFAULT 'pending',
  completeness TEXT NOT NULL DEFAULT 'unknown',
  discovered_count INTEGER NOT NULL DEFAULT 0,
  imported_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(sync_run_id, relation_type, collection_key),
  FOREIGN KEY(sync_run_id) REFERENCES sync_run(id)
);

CREATE TABLE IF NOT EXISTS content_classification (
  content_id TEXT PRIMARY KEY,
  topic TEXT NOT NULL DEFAULT '未分类',
  keywords_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'local_rules',
  updated_at TEXT NOT NULL,
  FOREIGN KEY(content_id) REFERENCES content(id)
);

CREATE INDEX IF NOT EXISTS idx_source_account_platform_state ON source_account(platform, connection_state);
CREATE INDEX IF NOT EXISTS idx_platform_collection_account ON platform_collection(source_account_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_sync_run_account_updated ON sync_run(source_account_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_run_status ON sync_run(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_event_run ON sync_run_event(sync_run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_sync_seen_relation_scope ON sync_seen_relation(sync_run_id, relation_type, collection_key);
CREATE INDEX IF NOT EXISTS idx_sync_run_scope_status ON sync_run_scope(sync_run_id, status);
CREATE INDEX IF NOT EXISTS idx_relation_time ON user_relation(relation_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_synced ON content(last_synced_at DESC);

-- ── 租户索引（v0.0.0.7 / T01）────────────────────────────────────────
-- 每个用户可见读取都必须带 user_id，这些索引让那条路径不至于全表扫。
CREATE INDEX IF NOT EXISTS idx_source_account_user ON source_account(user_id, platform);
CREATE INDEX IF NOT EXISTS idx_relation_user ON user_relation(user_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_relation_user_time ON user_relation(user_id, relation_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_platform_collection_user ON platform_collection(user_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_sync_run_user ON sync_run(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_user ON session(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_identity_user ON oauth_identity(user_id);

-- ── 有界 Cookie 托管（v0.0.0.7 / T05）──────────────────────────────
--
-- 只放西方三源（X / Instagram / YouTube）的会话，密文入库。
-- 国内平台**永不出现在这张表里**：它们的 Cookie 一步都不离开 Owner 的浏览器
-- （INV-DOMESTIC-COOKIE-STAYS）。拒绝发生在写入路径上，不是靠这里的 CHECK
-- 兜底——但 CHECK 仍然写上，因为"应用层记得拦"和"库里不可能存在"是两件事，
-- 后者才是不变量。
--
-- 密文直接存 BLOB 而不是存文件路径：撤销必须是一条 DELETE 就干净，
-- 存路径的话删表行只是删了指针，密文还躺在磁盘上，"撤销后库中无残留"就成了假话。
--
-- 这里存的**只有密文**。明文从进程内存到 age 子进程，落地时已经是密文；
-- 解密只发生在 materialize() 的 0600 临时文件里，用完即删，永不进持久卷。
CREATE TABLE IF NOT EXISTS platform_credential (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  platform TEXT NOT NULL CHECK(platform IN ('x','instagram','youtube')),
  algorithm TEXT NOT NULL DEFAULT 'age-x25519',
  recipient_fingerprint TEXT NOT NULL,
  cipher BLOB NOT NULL,
  cipher_sha256 TEXT NOT NULL,
  cipher_byte_size INTEGER NOT NULL,
  -- 只记形态，不记内容：条数用于界面显示"已连接"，永远不存 cookie 名或值。
  cookie_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT,
  UNIQUE(user_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_platform_credential_user ON platform_credential(user_id, platform);
