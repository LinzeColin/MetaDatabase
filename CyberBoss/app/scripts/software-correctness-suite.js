"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const SOFTWARE_CORRECTNESS_SCHEMA = "cyberboss.software-correctness.v1";
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");

const FROZEN_CORE_SLICES = Object.freeze([
  Object.freeze({
    id: "install_build_start",
    test_files: Object.freeze([
      "app/test/cloud-supervisor.test.js",
      "tests/cloud-install-layout.test.js",
      "tests/cloud-process-family.test.js",
      "tests/cloud-runtime-version.test.js",
    ]),
  }),
  Object.freeze({
    id: "migration_compatibility",
    test_files: Object.freeze(["app/test/runtime-spool.test.js"]),
  }),
  Object.freeze({
    id: "inbox_crash_recovery",
    test_files: Object.freeze(["app/test/durable-inbox-crash-cut.test.js"]),
  }),
  Object.freeze({
    id: "outbox_crash_recovery",
    test_files: Object.freeze(["app/test/durable-outbox-crash-cut.test.js"]),
  }),
  Object.freeze({
    id: "scheduler_singleton",
    test_files: Object.freeze(["app/test/job-scheduler.test.js"]),
  }),
  Object.freeze({
    id: "canonical_conflict_privacy",
    test_files: Object.freeze([
      "app/test/canonical-sync.test.js",
      "tests/canonical-sync.test.js",
    ]),
  }),
  Object.freeze({
    id: "timeline_status_access",
    test_files: Object.freeze([
      "app/test/canonical-timeline-projection.test.js",
      "app/test/canonical-status-export.test.js",
      "app/test/canonical-access-domain.test.js",
      "tests/canonical-timeline.test.js",
      "tests/canonical-status.test.js",
      "tests/canonical-access-plan.test.js",
    ]),
  }),
  Object.freeze({
    id: "backup_restore",
    test_files: Object.freeze([
      "app/test/canonical-backup-runtime.test.js",
      "tests/canonical-backup-runtime.test.js",
    ]),
  }),
  Object.freeze({
    id: "resource_self_heal",
    test_files: Object.freeze([
      "app/test/canonical-operations-policy.test.js",
      "tests/canonical-operations-plan.test.js",
    ]),
  }),
  Object.freeze({
    id: "rollback_discrimination",
    test_files: Object.freeze(["app/test/software-correctness-suite.test.js"]),
  }),
]);

const SENSITIVE_ENVIRONMENT = /TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|COOKIE|SESSION|PRIVATE_KEY|ACCESS_KEY|API_KEY|OPENAI|CODEX|WECHAT|CLOUDFLARE|GITHUB|^(AWS_|OCI_|CF_|GH_|SSH_)/i;

function assertFrozenCoreSuite(slices = FROZEN_CORE_SLICES) {
  if (!Array.isArray(slices) || slices.length !== 10) {
    throw codedError("FROZEN_CORE_SUITE_INVALID", "slice_count");
  }
  const ids = new Set();
  const files = new Set();
  for (const slice of slices) {
    if (!slice || !/^[a-z0-9_]+$/.test(String(slice.id || "")) || ids.has(slice.id)) {
      throw codedError("FROZEN_CORE_SUITE_INVALID", "slice_id");
    }
    ids.add(slice.id);
    if (!Array.isArray(slice.test_files) || slice.test_files.length === 0) {
      throw codedError("FROZEN_CORE_SUITE_INVALID", "slice_files");
    }
    for (const testFile of slice.test_files) {
      if (
        typeof testFile !== "string"
        || !/^(?:app\/test|tests)\/[A-Za-z0-9_.-]+\.test\.js$/.test(testFile)
        || files.has(testFile)
      ) {
        throw codedError("FROZEN_CORE_SUITE_INVALID", "test_file");
      }
      files.add(testFile);
    }
  }
  if (!ids.has("migration_compatibility") || !ids.has("rollback_discrimination")) {
    throw codedError("FROZEN_CORE_SUITE_INVALID", "required_slice");
  }
  return true;
}

function credentialFreeEnvironment(environment = process.env) {
  const clean = {};
  let removed = 0;
  for (const [key, value] of Object.entries(environment)) {
    if (SENSITIVE_ENVIRONMENT.test(key)) {
      removed += 1;
      continue;
    }
    clean[key] = value;
  }
  return { environment: clean, removed };
}

function defaultRunner({ command, cwd, environment }) {
  return spawnSync(command[0], command.slice(1), {
    cwd,
    env: environment,
    encoding: "utf8",
    timeout: 300000,
  });
}

function runFrozenCoreSuite({
  runner = defaultRunner,
  projectRoot = PROJECT_ROOT,
  environment = process.env,
  slices = FROZEN_CORE_SLICES,
} = {}) {
  assertFrozenCoreSuite(slices);
  const scrubbed = credentialFreeEnvironment(environment);
  const results = [];
  for (const slice of slices) {
    const command = [process.execPath, "--test", ...slice.test_files];
    let outcome;
    try {
      outcome = runner({
        slice,
        command,
        cwd: projectRoot,
        environment: scrubbed.environment,
      }) || {};
    } catch (error) {
      outcome = { status: null, error: error?.code || error?.name || "runner_exception" };
    }
    const passed = outcome.status === 0 && !outcome.error;
    results.push({ id: slice.id, status: passed ? "passed" : "failed" });
  }
  const failed = results.filter((result) => result.status !== "passed").map((result) => result.id);
  const passed = failed.length === 0;
  return {
    schema_version: SOFTWARE_CORRECTNESS_SCHEMA,
    status: passed ? "passed" : "failed",
    gate: passed ? "candidate_eligible_for_next_native_task" : "discard_candidate_keep_accepted_baseline",
    frozen_slice_count: slices.length,
    slice_results: results,
    failed_slices: failed,
    migration_compatibility: resultFor(results, "migration_compatibility"),
    rollback_discrimination: resultFor(results, "rollback_discrimination"),
    deployment_mutations: 0,
    network_or_provider_operations: 0,
    real_time_waits: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
    credential_named_environment_keys_removed: scrubbed.removed,
  };
}

function buildPostdeployAutomation() {
  assertFrozenCoreSuite();
  return {
    schema_version: SOFTWARE_CORRECTNESS_SCHEMA,
    status: "passed",
    mode: "postdeploy_nonblocking",
    trigger: "manual_or_ci",
    frozen_slice_count: FROZEN_CORE_SLICES.length,
    required_followup: [
      "status_summary",
      "incident_or_recovery_summary",
      "next_release_backlog",
    ],
    current_deployment_blocked: false,
    next_native_task_blocked: false,
    blocking_wait_nodes: 0,
    real_time_waits: 0,
    deployment_mutations: 0,
    network_or_provider_operations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  };
}

function resultFor(results, id) {
  return results.find((result) => result.id === id)?.status || "not_run";
}

function codedError(code, detail) {
  const error = new Error(`${code}:${detail}`);
  error.code = code;
  return error;
}

function parseMode(argv) {
  if (argv.length !== 1 || !argv[0].startsWith("--mode=")) {
    throw codedError("SOFTWARE_SUITE_ARGUMENT_INVALID", "mode_required");
  }
  const mode = argv[0].slice("--mode=".length);
  if (!new Set(["predeploy", "postdeploy"]).has(mode)) {
    throw codedError("SOFTWARE_SUITE_ARGUMENT_INVALID", "mode_value");
  }
  return mode;
}

function main(argv = process.argv.slice(2)) {
  try {
    const mode = parseMode(argv);
    const receipt = mode === "predeploy" ? runFrozenCoreSuite() : buildPostdeployAutomation();
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
    if (mode === "predeploy") {
      process.stdout.write(`FROZEN_CORE_SUITE=${receipt.status === "passed" ? "PASS" : "FAIL"}\n`);
      return receipt.status === "passed" ? 0 : 1;
    }
    process.stdout.write("POSTDEPLOY_AUTOMATION=PASS\n");
    return 0;
  } catch (error) {
    process.stderr.write(`${error?.code || "SOFTWARE_SUITE_ERROR"}\n`);
    return 2;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  FROZEN_CORE_SLICES,
  SOFTWARE_CORRECTNESS_SCHEMA,
  assertFrozenCoreSuite,
  buildPostdeployAutomation,
  credentialFreeEnvironment,
  main,
  runFrozenCoreSuite,
};
