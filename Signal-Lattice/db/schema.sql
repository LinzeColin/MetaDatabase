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
CREATE TABLE IF NOT EXISTS skill_signal_inputs (
  skill_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  as_of TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(skill_id, symbol, market)
);
CREATE TABLE IF NOT EXISTS market_snapshots (
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  as_of TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(symbol, market)
);
CREATE TABLE IF NOT EXISTS decision_snapshots (
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(symbol, market, receipt_sha256)
);

-- North-star minute cycle runtime
CREATE TABLE IF NOT EXISTS minute_cycles (
  cycle_id TEXT PRIMARY KEY,
  scheduled_for TEXT NOT NULL UNIQUE,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  state TEXT NOT NULL CHECK(state IN ('RUNNING','COMPLETED','DEGRADED','FAILED','SKIPPED_OVERLAP')),
  source_commit TEXT,
  universe_sha256 TEXT,
  market_snapshot_sha256 TEXT,
  active_skill_count INTEGER NOT NULL DEFAULT 0,
  completed_skill_count INTEGER NOT NULL DEFAULT 0,
  failed_skill_count INTEGER NOT NULL DEFAULT 0,
  recommendation_json TEXT,
  receipt_sha256 TEXT,
  error_json TEXT
);
CREATE TABLE IF NOT EXISTS minute_skill_runs (
  cycle_id TEXT NOT NULL REFERENCES minute_cycles(cycle_id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL,
  skill_version TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('RUNNING','PASS','ABSTAIN','FAILED','TIMEOUT','QUARANTINED')),
  started_at TEXT NOT NULL,
  completed_at TEXT,
  duration_ms INTEGER,
  input_sha256 TEXT NOT NULL,
  output_sha256 TEXT,
  output_json TEXT,
  error_code TEXT,
  isolation_backend TEXT NOT NULL,
  PRIMARY KEY(cycle_id, skill_id)
);
CREATE TABLE IF NOT EXISTS skill_runtime_registry (
  skill_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  skill_version TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','RETIRED','REMOVED','QUARANTINED')),
  compatibility_state TEXT NOT NULL,
  runtime_profile TEXT NOT NULL,
  lineage_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  promoted_at TEXT,
  lkg_manifest_json TEXT,
  lkg_manifest_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS minute_market_snapshots (
  cycle_id TEXT NOT NULL REFERENCES minute_cycles(cycle_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  as_of TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  PRIMARY KEY(cycle_id, symbol, market)
);
CREATE TABLE IF NOT EXISTS universe_members (
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  active INTEGER NOT NULL CHECK(active IN (0,1)),
  priority INTEGER NOT NULL DEFAULT 100,
  source TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL,
  PRIMARY KEY(symbol, market)
);
CREATE TABLE IF NOT EXISTS skill_reliability (
  skill_id TEXT NOT NULL,
  market TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  weight REAL NOT NULL,
  sample_count INTEGER NOT NULL,
  brier_score REAL,
  directional_accuracy REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(skill_id, market, horizon_days)
);
CREATE TABLE IF NOT EXISTS skill_outcome_queue (
  cycle_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  forecast_as_of TEXT NOT NULL,
  maturity_at TEXT NOT NULL,
  reference_price REAL NOT NULL,
  direction INTEGER NOT NULL,
  confidence REAL NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('PENDING','SCORED','EXPIRED')),
  outcome_json TEXT,
  PRIMARY KEY(cycle_id, skill_id, symbol, market)
);
CREATE TABLE IF NOT EXISTS source_reconcile_events (
  event_id TEXT PRIMARY KEY,
  source_commit TEXT NOT NULL,
  event_type TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  previous_json TEXT,
  current_json TEXT,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_minute_cycles_scheduled ON minute_cycles(scheduled_for DESC);
CREATE INDEX IF NOT EXISTS idx_skill_runs_cycle ON minute_skill_runs(cycle_id,state);
CREATE INDEX IF NOT EXISTS idx_outcomes_maturity ON skill_outcome_queue(state,maturity_at);
