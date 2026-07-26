PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

BEGIN IMMEDIATE;

ALTER TABLE jobs ADD COLUMN scheduler_managed INTEGER NOT NULL DEFAULT 0
  CHECK (scheduler_managed IN (0, 1));
ALTER TABLE jobs ADD COLUMN lease_heartbeat_at TEXT;
ALTER TABLE jobs ADD COLUMN dispatch_started_at TEXT;
ALTER TABLE jobs ADD COLUMN cancel_requested_at TEXT;
ALTER TABLE jobs ADD COLUMN runtime_thread_hash TEXT;
ALTER TABLE jobs ADD COLUMN runtime_turn_hash TEXT;
ALTER TABLE jobs ADD COLUMN last_runtime_event_at TEXT;

CREATE UNIQUE INDEX idx_jobs_single_active_runtime
ON jobs((1))
WHERE operation_class <> 'command'
  AND status IN ('running', 'waiting_approval');

CREATE INDEX idx_jobs_control_queue
ON jobs(operation_class, status, created_at, id);

CREATE TRIGGER jobs_scheduler_runtime_lease_guard
BEFORE UPDATE ON jobs
WHEN NEW.scheduler_managed = 1
  AND NEW.operation_class <> 'command'
  AND NEW.status IN ('running', 'waiting_approval')
  AND (
    NEW.lease_owner IS NULL
    OR NEW.lease_heartbeat_at IS NULL
    OR NEW.lease_expires_at IS NULL
  )
BEGIN
  SELECT RAISE(ABORT, 'scheduler_runtime_lease_required');
END;

CREATE TRIGGER jobs_scheduler_command_control_lease_guard
BEFORE UPDATE ON jobs
WHEN NEW.scheduler_managed = 1
  AND NEW.operation_class = 'command'
  AND NEW.status = 'running'
  AND (
    NEW.lease_owner IS NULL
    OR NEW.lease_heartbeat_at IS NULL
    OR NEW.lease_expires_at IS NULL
  )
BEGIN
  SELECT RAISE(ABORT, 'scheduler_command_control_lease_required');
END;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  3,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB-220',
  '__MIGRATION_003_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
