PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

-- Rebuildable operational journal only. User credentials, note content, book
-- metadata, search text and export archives are forbidden by design.
CREATE TABLE IF NOT EXISTS runtime_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  event_status TEXT NOT NULL CHECK (event_status IN ('ok','operational','degraded','failed','unknown')),
  occurred_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  CHECK (json_valid(payload_json))
) STRICT;
CREATE INDEX IF NOT EXISTS idx_runtime_events_occurred
  ON runtime_events(occurred_at, event_id);

CREATE TABLE IF NOT EXISTS health_samples (
  sample_id INTEGER PRIMARY KEY,
  checked_at TEXT NOT NULL,
  service_status TEXT NOT NULL CHECK (service_status IN ('operational','degraded','unconfigured','unknown')),
  health_http_status INTEGER,
  version_http_status INTEGER,
  latency_ms REAL,
  app_version TEXT,
  source_skill_version TEXT,
  error_code TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  CHECK (json_valid(payload_json))
) STRICT;
CREATE INDEX IF NOT EXISTS idx_health_samples_checked
  ON health_samples(checked_at, sample_id);

CREATE TABLE IF NOT EXISTS outbox (
  outbox_id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 32),
  last_error TEXT,
  CHECK (json_valid(payload_json))
) STRICT;
CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox(delivered_at, created_at, outbox_id);

CREATE TABLE IF NOT EXISTS cursors (
  cursor_name TEXT PRIMARY KEY,
  cursor_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS release_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  current_commit TEXT NOT NULL,
  current_saved_version TEXT NOT NULL,
  current_production_version TEXT NOT NULL,
  production_origin TEXT NOT NULL,
  previous_commit TEXT,
  previous_saved_version TEXT,
  previous_production_version TEXT,
  updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS backup_state (
  backup_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  snapshot_path TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  sqlite_integrity TEXT NOT NULL,
  r2_status TEXT NOT NULL,
  oci_status TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  CHECK (json_valid(details_json))
) STRICT;

PRAGMA user_version=6;
