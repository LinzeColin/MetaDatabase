"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const project = path.resolve(__dirname, "..");
const kit = path.join(
  project,
  "docs/product_design/v0.0.0.4/implementation-kit",
);
const zeroCommit = "0000000000000000000000000000000000000000";

function read(relative) {
  return fs.readFileSync(path.join(project, relative), "utf8");
}

function run(command, args) {
  return spawnSync(command, args, {
    cwd: project,
    encoding: "utf8",
    timeout: 30000,
  });
}

test("versioned spool migrations preserve the starter and remain additive", () => {
  const starter = read(
    "docs/product_design/v0.0.0.4/implementation-kit/sql/runtime-spool.sql",
  );
  const migration1 = read("app/migrations/001_runtime_spool.sql");
  const migration2 = read(
    "app/migrations/002_cb200_retention_and_transitions.sql",
  );
  assert.equal(migration1, starter);
  assert.doesNotMatch(migration2, /\b(?:DROP|RENAME|VACUUM)\b/i);
  assert.match(migration2, /ALTER TABLE schema_migrations ADD COLUMN/);
  assert.match(migration2, /CREATE TABLE job_state_transitions/);
  assert.match(migration2, /CREATE TRIGGER jobs_status_transition_guard/);
  assert.match(migration2, /CREATE TRIGGER job_events_immutable_delete_guard/);
  assert.equal(
    [...migration2.matchAll(/\('[a-z_]+', '[a-z_]+'\)/g)].length,
    21,
  );
});

test("the repository centralizes SQL, encryption, IDs, TTL and reconciliation", () => {
  const adapter = read("app/src/services/db/database-adapter.js");
  const stateMachine = read("app/src/services/jobs/job-state-machine.js");
  for (const marker of [
    "DatabaseSync",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "aes-256-gcm",
    "deriveStableIds",
    "acceptInbound",
    "transitionJob",
    "redactExpiredPayloads",
    "reconcileCanonicalEventIds",
  ]) {
    assert.match(adapter, new RegExp(marker));
  }
  assert.match(stateMachine, /IllegalJobTransitionError/);
  assert.match(stateMachine, /canonical_pending/);
  assert.doesNotMatch(adapter, /console\.(?:log|error|warn)/);
});

test("read-only installer and acceptance checks perform no live mutation", () => {
  const installer = run("bash", [
    path.join(kit, "scripts/install-runtime-spool.sh"),
    "--check",
    "--release-id",
    zeroCommit,
  ]);
  assert.equal(installer.status, 0, installer.stderr);
  assert.match(installer.stdout, /RUNTIME_SPOOL_INSTALL_CHECK=PASS/);
  assert.match(installer.stdout, /persistent_writes=false/);
  assert.match(installer.stdout, /live_commands=false/);
  assert.match(installer.stdout, /service_started=false/);

  const acceptance = run("bash", [
    path.join(kit, "scripts/accept-runtime-spool.sh"),
    "--check",
    "--release-id",
    zeroCommit,
  ]);
  assert.equal(acceptance.status, 0, acceptance.stderr);
  assert.match(acceptance.stdout, /RUNTIME_SPOOL_ACCEPTANCE_CHECK=PASS/);
  assert.match(acceptance.stdout, /real_credential_reads=false/);
  assert.match(acceptance.stdout, /provider_writes=false/);
  assert.match(acceptance.stdout, /private_database_operations=false/);
  assert.match(acceptance.stdout, /pg_2_executed=false/);
});

test("artifact/install contracts bind exact source and strict compliance", () => {
  const builder = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const acceptance = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-runtime-spool.sh",
  );
  const acceptanceRunner = read("app/scripts/runtime-spool-acceptance.js");
  const contract = read("docs/governance/RUN_CONTRACT_P2_1_CB_200.md");
  for (const source of [builder, installer, acceptance, contract]) {
    assert.match(source, /CB-200/);
  }
  for (const source of [builder, installer, contract]) {
    assert.match(source, /AGPL-3\.0-only AND GPL-3\.0-only/);
    assert.match(source, /upstream_clarification_received/);
  }
  assert.match(builder, /"real_canonical_sync": False/);
  assert.match(builder, /"channel_poll_integrated": False/);
  assert.match(installer, /switch_current == false/);
  assert.match(acceptance, /service_must_be_inactive/);
  assert.match(acceptanceRunner, /path\.basename\(databasePath\)/);
  assert.match(acceptanceRunner, /`\\?\$\{databaseName\}-shm`/);
  assert.match(acceptanceRunner, /`\\?\$\{databaseName\}-wal`/);
  assert.match(contract, /不得修改 channel poll/);
  assert.match(contract, /不创建新 repo/);
  assert.match(contract, /本 Run 不 push/);
});

test("CB-200 scripts avoid fixed waits and compile without cache writes", () => {
  for (const relative of [
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-spool.sh",
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-runtime-spool.sh",
  ]) {
    const source = read(relative);
    assert.doesNotMatch(source, /^\s*sleep(?:\s|$)/m, relative);
    const shell = run("bash", ["-n", path.join(project, relative)]);
    assert.equal(shell.status, 0, `${relative}:${shell.stderr}`);
  }
  for (const relative of [
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-runtime-spool-artifacts.py",
    "scripts/validate_cb200.py",
  ]) {
    const parsed = run("python3", [
      "-c",
      "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
      path.join(project, relative),
    ]);
    assert.equal(parsed.status, 0, `${relative}:${parsed.stderr}`);
  }
});
