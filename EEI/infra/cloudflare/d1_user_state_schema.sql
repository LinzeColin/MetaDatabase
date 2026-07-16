-- EEI cloud user-state layer (S10PBT01, Cloudflare D1 / SQLite dialect).
-- 云端即真相: user state written in the cloud lives in the cloud; there is
-- no sync-back queue to the local factory (ADP doctrine). Publication
-- tables stay one-way local -> cloud and are defined separately in
-- d1_publication_schema.sql.

CREATE TABLE IF NOT EXISTS saved_views (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  workspace_key TEXT NOT NULL,
  state_json TEXT NOT NULL,
  schema_version TEXT NOT NULL DEFAULT 'saved-view-v1',
  current_version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_view_versions (
  view_id TEXT NOT NULL REFERENCES saved_views(id),
  version_no INTEGER NOT NULL,
  state_json TEXT NOT NULL,
  change_note TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (view_id, version_no)
);

CREATE TABLE IF NOT EXISTS watchlists (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
  watchlist_id TEXT NOT NULL REFERENCES watchlists(id),
  entity_id TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY (watchlist_id, entity_id)
);

CREATE TABLE IF NOT EXISTS exploration_log (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  action TEXT NOT NULL,
  focus_entity_id TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exploration_log_created
  ON exploration_log(created_at);

-- S10PBT02: cloud incremental-collection run log (7x24 evidence heartbeat).
CREATE TABLE IF NOT EXISTS cloud_run_log (
  id TEXT PRIMARY KEY,
  trigger TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  rotation_slice INTEGER,
  scope_json TEXT,
  new_filings_count INTEGER NOT NULL DEFAULT 0,
  detail_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_cloud_run_log_started
  ON cloud_run_log(started_at);
