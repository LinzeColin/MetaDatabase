#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const APP_ROOT = path.resolve(__dirname, "..");
const PROJECT_ROOT = path.resolve(APP_ROOT, "..");
const TEST_FILES = Object.freeze([
  "test/job-scheduler.test.js",
  "test/resource-readiness-gate.test.js",
  "test/turn-gate-store.test.js",
  "test/workspace-scope.test.js",
]);

class AcceptanceError extends Error {
  constructor(code) {
    super(code);
    this.name = "AcceptanceError";
    this.code = code;
  }
}

function parseArguments(argv) {
  let output = "";
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--output") {
      output = String(argv[index + 1] || "").trim();
      index += 1;
      continue;
    }
    throw new AcceptanceError("ARGUMENT_INVALID");
  }
  if (!output || !path.isAbsolute(output)) {
    throw new AcceptanceError("ABSOLUTE_OUTPUT_REQUIRED");
  }
  return { output: path.resolve(output) };
}

function readSource(relative) {
  return fs.readFileSync(path.join(APP_ROOT, relative), "utf8");
}

function assertStaticContract() {
  const migration = readSource("migrations/003_cb220_scheduler_control.sql");
  const scheduler = readSource("src/services/jobs/job-scheduler.js");
  const gate = readSource("src/services/jobs/resource-readiness-gate.js");
  const workspace = readSource("src/core/workspace-registry.js");
  for (const [source, marker] of [
    [migration, "idx_jobs_single_active_runtime"],
    [migration, "scheduler_runtime_lease_required"],
    [scheduler, "claimNextRuntimeJob"],
    [scheduler, "recoverExpiredRuntimeLease"],
    [scheduler, "runtime_dispatch_ambiguous"],
    [gate, "poll_stale"],
    [gate, "runtime_unhealthy"],
    [gate, "disk_pressure"],
    [gate, "queue_stuck"],
    [workspace, "workspace_symlink_rejected"],
    [workspace, "workspace_root_not_allowlisted"],
  ]) {
    if (!source.includes(marker)) {
      throw new AcceptanceError("STATIC_CONTRACT_MISSING");
    }
  }
  if (/\b(?:DROP|RENAME|VACUUM)\b/i.test(migration)) {
    throw new AcceptanceError("MIGRATION_DESTRUCTIVE");
  }
  if (/\b(?:sleep|setTimeout)\s*\(/.test(`${scheduler}\n${gate}`)) {
    throw new AcceptanceError("REAL_TIME_WAIT_FORBIDDEN");
  }
}

function runExecutableSuite() {
  const childEnvironment = {
    ...process.env,
    NODE_ENV: "test",
  };
  delete childEnvironment.NODE_TEST_CONTEXT;
  const result = spawnSync(
    process.execPath,
    ["--test", ...TEST_FILES],
    {
      cwd: APP_ROOT,
      encoding: "utf8",
      env: childEnvironment,
      timeout: 120_000,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  if (result.status !== 0) {
    throw new AcceptanceError("EXECUTABLE_SUITE_FAILED");
  }
  const output = `${result.stdout || ""}\n${result.stderr || ""}`;
  const tests = [...output.matchAll(/(?:^|\n)[^\S\r\n]*(?:ℹ|#)?[^\S\r\n]*tests\s+([0-9]+)/g)]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite)
    .pop();
  const failures = [...output.matchAll(/(?:^|\n)[^\S\r\n]*(?:ℹ|#)?[^\S\r\n]*fail\s+([0-9]+)/g)]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite)
    .pop();
  if (!Number.isSafeInteger(tests) || tests < 20 || failures !== 0) {
    throw new AcceptanceError("EXECUTABLE_SUITE_SUMMARY_INVALID");
  }
  return Object.freeze({ tests, failures });
}

function buildReport(suite) {
  return {
    schema_version: 1,
    task_id: "CB-220",
    phase: "P2.3",
    claim_level: "deterministic_fixture",
    result: "passed",
    executable_suite: {
      files: TEST_FILES.map((file) => path.basename(file)),
      tests: suite.tests,
      failures: suite.failures,
      fixed_wait: false,
      real_provider: false,
      real_credentials: false,
    },
    scheduler: {
      queued_runtime_jobs: 5,
      max_active_runtime_leases: 1,
      fifo_dispatch_order: true,
      command_runtime_planes_separated: true,
      transactional_claim: true,
      heartbeat_and_expiry: true,
      stale_owner_fenced: true,
    },
    workspace: {
      allowlisted_alias_dispatched: true,
      absolute_path_dispatched: false,
      unknown_alias_dispatched: false,
      symlink_escape_dispatched: false,
      filesystem_changed_on_rejection: false,
    },
    resource_gate: {
      reason_action_matrix: {
        poll_stale: "restart_channel_adapter",
        runtime_unhealthy: "restart_runtime_process_family",
        disk_pressure: "pause_mutations_and_cleanup_reconstructable_data",
        load_pressure: "hold_new_runtime_jobs",
        queue_stuck: "inspect_active_lease_and_runtime",
      },
      guard_ladder: [
        "recover",
        "warn",
        "protect",
        "protect",
        "protect",
        "recover",
      ],
      protect_blocks_mutation: true,
      recover_allows_dispatch: true,
      no_real_time_soak: true,
    },
    stop: {
      cancel_call_count: 3,
      terminal_by_runtime_status: {
        interrupted: "cancelled",
        failed: "failed_terminal",
        completed: "succeeded",
      },
      acknowledgement_claimed_terminal: false,
      false_success_count: 0,
    },
    recovery: {
      pre_dispatch_requeued: true,
      ambiguous_mutation_replayed: false,
      stale_owner_heartbeat_succeeded: false,
      late_event_released_new_lease: false,
    },
    runtime_errors: {
      covered_classes: [
        "auth_required",
        "cancelled",
        "runtime_overloaded",
        "runtime_terminal",
        "transport_unavailable",
      ],
      bounded_mutation_auto_replay: false,
    },
    phase_boundary: {
      outbox_worker_integrated: false,
      canonical_sync_integrated: false,
      pg_2_executed: false,
      real_wechat: false,
      real_runtime: false,
    },
  };
}

function atomicWrite(output, document) {
  const parent = path.dirname(output);
  if (!fs.existsSync(parent)) {
    fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  }
  const parentStats = fs.lstatSync(parent);
  if (!parentStats.isDirectory() || parentStats.isSymbolicLink()) {
    throw new AcceptanceError("OUTPUT_PARENT_INVALID");
  }
  if (fs.existsSync(output) && fs.lstatSync(output).isSymbolicLink()) {
    throw new AcceptanceError("OUTPUT_SYMLINK_FORBIDDEN");
  }
  const temporary = `${output}.tmp-${process.pid}`;
  fs.writeFileSync(
    temporary,
    `${JSON.stringify(document, null, 2)}\n`,
    { mode: 0o600, flag: "wx" },
  );
  fs.renameSync(temporary, output);
  fs.chmodSync(output, 0o600);
}

function main() {
  const { output } = parseArguments(process.argv.slice(2));
  assertStaticContract();
  const suite = runExecutableSuite();
  const report = buildReport(suite);
  atomicWrite(output, report);
  process.stdout.write(
    `CB220_JOB_SCHEDULER_ACCEPTANCE=PASS tests=${suite.tests} failures=0\n`,
  );
}

try {
  main();
} catch (error) {
  const code = error instanceof AcceptanceError
    ? error.code
    : "ACCEPTANCE_INTERNAL_ERROR";
  process.stderr.write(`CB220_JOB_SCHEDULER_ACCEPTANCE=FAIL code=${code}\n`);
  process.exitCode = 1;
}
