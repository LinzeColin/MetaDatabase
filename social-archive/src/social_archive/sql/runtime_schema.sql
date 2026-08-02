PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS source_account (
  id TEXT PRIMARY KEY,
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
  UNIQUE(platform, external_content_id),
  UNIQUE(platform, canonical_url)
);

CREATE TABLE IF NOT EXISTS user_relation (
  id TEXT PRIMARY KEY,
  source_account_id TEXT,
  content_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  collection_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_source_account_platform_state ON source_account(platform, connection_state);
CREATE INDEX IF NOT EXISTS idx_platform_collection_account ON platform_collection(source_account_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_sync_run_account_updated ON sync_run(source_account_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_run_status ON sync_run(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_event_run ON sync_run_event(sync_run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_sync_seen_relation_scope ON sync_seen_relation(sync_run_id, relation_type, collection_key);
CREATE INDEX IF NOT EXISTS idx_sync_run_scope_status ON sync_run_scope(sync_run_id, status);
