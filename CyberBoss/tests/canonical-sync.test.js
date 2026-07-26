"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const KIT = path.join(
  PROJECT_ROOT,
  "docs/product_design/v0.0.0.4/implementation-kit",
);
const RELEASE_COMMIT = "b".repeat(40);

function source(relative) {
  return fs.readFileSync(path.join(PROJECT_ROOT, relative), "utf8");
}

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb240-contract-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test("CB-240 contract retains the frozen TaskPack and phase boundary", () => {
  const dag = source(
    "docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
  );
  const task = dag.slice(
    dag.indexOf("- id: CB-240"),
    dag.indexOf("- id: CB-300"),
  );
  for (const marker of [
    "phase: P2.5",
    "- CB-120",
    "- CB-200",
    "- CB-230",
    "- AC-030",
    "- AC-031",
    "- AC-032",
    "- AC-033",
    "pass_gate: PG-2",
  ]) {
    assert.match(
      task,
      new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    );
  }
  const contract = source("docs/governance/RUN_CONTRACT_P2_5_CB_240.md");
  for (const marker of [
    "8793e186f4baa2767dc3da0378492ffa17984d4d",
    "Private-MetaDatabase",
    "ingest|get|list|verify",
    "same event ID/different record hash",
    "CB-300",
    "PG-2",
    "不创建新 repo",
    "AGPL-3.0-only AND GPL-3.0-only",
    "activation_pending",
  ]) {
    assert.match(
      contract,
      new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
    );
  }
});

test("schema v5 and canonical objects are additive immutable and deterministic", () => {
  const migration = source("app/migrations/005_cb240_canonical_sync.sql");
  assert.doesNotMatch(migration, /\b(?:DROP|RENAME|VACUUM)\b/i);
  for (const marker of [
    "ALTER TABLE sync_spool ADD COLUMN batch_id",
    "batch_event_set_sha256",
    "manifest_record_sha256",
    "remote_object_path",
    "verified_at",
    "retry_after_ms",
    "last_receipt_sha256",
    "sync_spool_identity_immutable_guard",
    "sync_spool_delete_guard",
  ]) {
    assert.match(migration, new RegExp(marker));
  }
  const canonical = source(
    "app/src/services/canonical/canonical-sync.js",
  );
  for (const marker of [
    "mapJobEventToCanonical",
    "encodeCanonicalBatch",
    "mtime: 0",
    "eventSetSha256",
    "NoClonePrivateDatabaseAdapter",
    "CanonicalSpoolCoordinator",
    "CanonicalDataWorker",
    "readRemoteCanonical",
    "rebuildCanonicalProjection",
    "CANONICAL_REMOTE_EVENT_CONFLICT",
  ]) {
    assert.match(canonical, new RegExp(marker));
  }
  assert.doesNotMatch(canonical, /\bgit\s+clone\b/i);
});

test("identity-separated worker and scheduler enforce no-clone and mutation protection", () => {
  const wrapper = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py",
  );
  assert.match(wrapper, /pwd\.getpwuid\(os\.geteuid\(\)\)\.pw_name/);
  assert.match(wrapper, /policy\["data"\]\["execution_identity"\]/);
  for (const operation of ["ingest", "get", "list", "verify"]) {
    assert.match(wrapper, new RegExp(`add_parser\\("${operation}"\\)`));
  }
  const dataCli = source("app/scripts/canonical-sync-data.js");
  const rebuildCli = source("app/scripts/canonical-rebuild.js");
  for (const cli of [dataCli, rebuildCli]) {
    assert.match(cli, /CANONICAL_DATA_IDENTITY_REQUIRED/);
    assert.match(cli, /NoClonePrivateDatabaseAdapter/);
  }
  const scheduler = source("app/src/services/jobs/job-scheduler.js");
  assert.match(scheduler, /canonicalMutationGuard/);
  assert.match(scheduler, /canonical_backlog_protect/);
  assert.match(scheduler, /operationClass: "read_only"/);
});

test("implementation kit keeps canonical units inactive and candidate-only", () => {
  const unit = source(
    "docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.service",
  );
  for (const marker of [
    "Type=oneshot",
    "User=cyberboss-data",
    "Group=cyberboss",
    "SupplementaryGroups=cyberboss-data",
    "canonical-sync-data.js",
    "ReadOnlyPaths=/opt/cyberboss-cloud /etc/cyberboss",
    "ReadWritePaths=/var/lib/cyberboss-data /var/lib/cyberboss/canonical-spool",
  ]) {
    assert.match(unit, new RegExp(marker));
  }
  const timer = source(
    "docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.timer",
  );
  assert.match(timer, /OnUnitActiveSec=1min/);
  assert.match(timer, /Persistent=false/);
  const builder = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const acceptance = source(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-canonical-sync.sh",
  );
  for (const value of [builder, installer, acceptance]) {
    assert.match(value, /CB-240/);
    assert.match(value, /P2\.5/);
    assert.match(value, /canonical-sync-report/);
    assert.match(value, /activation_pending/);
    assert.match(value, /pg_2_executed/);
  }
  assert.match(installer, /canonical_service_enabled_after/);
  assert.doesNotMatch(installer, /systemctl enable/);
  assert.doesNotMatch(installer, /systemctl start/);
  assert.match(acceptance, /private_database_operations=false/);
  assert.match(acceptance, /real_credential_reads=false/);
});

test("installer and acceptance check modes are read-only", () => {
  for (const [script, marker] of [
    ["install-canonical-sync.sh", "CANONICAL_SYNC_INSTALL_CHECK=PASS"],
    ["accept-canonical-sync.sh", "CANONICAL_SYNC_ACCEPTANCE_CHECK=PASS"],
  ]) {
    const result = spawnSync(
      "bash",
      [
        path.join(KIT, "scripts", script),
        "--check",
        "--release-id",
        RELEASE_COMMIT,
      ],
      {
        cwd: PROJECT_ROOT,
        encoding: "utf8",
        timeout: 30_000,
      },
    );
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, new RegExp(marker));
    assert.match(result.stdout, /persistent_writes=false/);
    assert.match(result.stdout, /service_started=false/);
  }
});

test("CB-240 executable acceptance proves bounded synthetic claims", (t) => {
  const directory = temporaryDirectory(t);
  const runtimeRoot = path.join(directory, "runtime");
  const output = path.join(directory, "output");
  const keyFile = path.join(directory, "synthetic.key");
  fs.mkdirSync(runtimeRoot, { mode: 0o700 });
  fs.mkdirSync(output, { mode: 0o700 });
  fs.writeFileSync(keyFile, Buffer.from("52".repeat(32), "hex"), {
    mode: 0o400,
  });
  const result = spawnSync(
    process.execPath,
    [
      path.join(
        PROJECT_ROOT,
        "app/scripts/canonical-sync-acceptance.js",
      ),
      "--runtime-root", runtimeRoot,
      "--key-file", keyFile,
      "--output-directory", output,
      "--release-commit", RELEASE_COMMIT,
      "--target-id-sha256", "7865f743d174",
    ],
    {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      timeout: 240_000,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  assert.equal(
    result.status,
    0,
    `status=${result.status} stdout=${result.stdout} stderr=${result.stderr}`,
  );
  assert.match(result.stdout, /CB240_CANONICAL_SYNC_ACCEPTANCE=PASS/);
  const report = JSON.parse(
    fs.readFileSync(
      path.join(output, "canonical-sync-report.json"),
      "utf8",
    ),
  );
  assert.equal(report.result, "passed");
  assert.equal(report.executable_suite.failures, 0);
  assert.equal(report.ac_030_rebuild.sqlite_present, false);
  assert.equal(report.ac_030_rebuild.canonical_event_count, 1000);
  assert.equal(report.ac_030_rebuild.terminal_job_count, 1000);
  assert.equal(report.ac_030_rebuild.r2_fixture_only, true);
  assert.equal(report.ac_031_batching_latency.terminal_jobs, 50);
  assert.ok(report.ac_031_batching_latency.latency_p95_seconds <= 60);
  assert.equal(report.ac_031_batching_latency.terminal_events, 1000);
  assert.equal(report.ac_031_batching_latency.set_diff, 0);
  assert.equal(
    report.ac_032_conflict_retry.concurrent_sync_groups,
    50,
  );
  assert.equal(report.ac_032_conflict_retry.initial_pending_groups, 3);
  assert.equal(report.ac_032_conflict_retry.outage_duration_seconds, 600);
  assert.equal(report.ac_032_conflict_retry.real_wait_calls, 0);
  assert.equal(report.ac_032_conflict_retry.set_diff, 0);
  assert.equal(
    report.ac_033_privacy.full_prompt_result_identity_hits,
    0,
  );
  assert.equal(report.ac_033_privacy.encryption_key_hits, 0);
  assert.equal(report.integrity_protection.last_write_wins, false);
  assert.equal(
    report.integrity_protection.bounded_mutation_allowed,
    false,
  );
  assert.deepEqual(
    report.canonical_truth.allowed_operations,
    ["ingest", "get", "list", "verify"],
  );
  assert.equal(
    report.boundaries.real_private_database_operation,
    false,
  );
  assert.equal(report.boundaries.private_database_activation_status, "activation_pending");
  assert.equal(report.boundaries.real_r2_operation, false);
  assert.equal(report.boundaries.cb_300_executed, false);
  assert.equal(report.boundaries.pg_2_executed, false);
  assert.doesNotMatch(
    JSON.stringify(report),
    /CB240-PRIVATE|wxid_|Authorization|\/Users\/|\/var\/lib\//,
  );
});

test("strict license source and unresolved conflict records remain frozen", () => {
  const sourceLock = JSON.parse(source("machine/source-lock.json"));
  assert.deepEqual(sourceLock.upstream_relationship, {
    automatic_sync_allowed: false,
    git_url_dependency_allowed: false,
    periodic_rebase_allowed: false,
    remote_allowed: false,
    runtime_source_fetch_allowed: false,
    submodule_allowed: false,
  });
  assert.equal(
    sourceLock.whereabouts_license_conflict.upstream_clarification_received,
    false,
  );
  assert.equal(
    sourceLock.whereabouts_license_conflict
      .preserve_original_license_and_source,
    true,
  );
  assert.deepEqual(
    new Set(
      sourceLock.whereabouts_license_conflict.compliance_expression
        .split("AND")
        .map((value) => value.trim()),
    ),
    new Set(["AGPL-3.0-only", "GPL-3.0-only"]),
  );
});
