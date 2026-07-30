PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=FULL;

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  request_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  result_json TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  number INTEGER NOT NULL,
  state TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  error_code TEXT,
  UNIQUE(job_id, number)
);
CREATE TABLE IF NOT EXISTS leases (
  resource_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  fencing_token INTEGER NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_journal (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('PENDING','SENT','FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
  symbol TEXT NOT NULL,
  action_type TEXT NOT NULL,
  valid_until TEXT NOT NULL,
  packet_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_snapshots (
  skill_id TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL,
  compatibility_state TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  promoted_at TEXT,
  PRIMARY KEY(skill_id, source_commit, content_sha256)
);
CREATE TABLE IF NOT EXISTS evolution_runs (
  run_id TEXT PRIMARY KEY,
  skill_id TEXT NOT NULL,
  champion_sha256 TEXT NOT NULL,
  challenger_sha256 TEXT,
  verdict TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS business_line_status (
  line_id TEXT NOT NULL,
  slice_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  state TEXT NOT NULL,
  measured INTEGER NOT NULL CHECK(measured IN (0,1)),
  evidence_ref TEXT,
  freshness TEXT NOT NULL,
  upstream_json TEXT NOT NULL,
  downstream_json TEXT NOT NULL,
  coupling_json TEXT NOT NULL,
  blocker TEXT,
  next_action TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(line_id, slice_id)
);
CREATE TABLE IF NOT EXISTS sync_cursor (
  sink_id TEXT PRIMARY KEY,
  cursor_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
