"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  CANDIDATE_MANIFEST_DIGEST,
  CANDIDATE_RELEASE_ID,
  DressRehearsalError,
  FROZEN_DRESS_REHEARSAL_STEPS,
  OPERATOR_RUNBOOK_DIGEST,
  buildActivationPlan,
  buildCleanStagingRehearsal,
} = require("../src/services/release/canonical-dress-rehearsal");

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

test("clean staging rehearsal is complete without promotion or hidden operator knowledge", () => {
  const report = buildCleanStagingRehearsal();

  assert.equal(report.status, "passed");
  assert.equal(report.decision, "rehearsal_complete_external_activation_pending");
  assert.equal(report.rehearsal_steps.length, 12);
  assert.equal(report.staging.clean_before_rehearsal, true);
  assert.equal(report.staging.clean_after_rehearsal, true);
  assert.equal(report.staging.current_switch, false);
  assert.equal(report.staging.source_code_knowledge_required, false);
  assert.equal(report.operator.command_count, 8);
  assert.equal(report.operator.runbook_digest, OPERATOR_RUNBOOK_DIGEST);
  assert.equal(report.candidate.release_id, CANDIDATE_RELEASE_ID);
  assert.equal(report.candidate.manifest_digest, CANDIDATE_MANIFEST_DIGEST);
  assert.equal(report.go_no_go.local_rehearsal, "go_local_only");
  assert.equal(report.go_no_go.production_promotion, "activation_pending");
  assert.equal(report.go_no_go.p0_failure_count, 0);
  assert.equal(report.external_activation.live_request_count_canary, "activation_pending");
  assert.equal(report.network_or_provider_operations, 0);
  assert.equal(report.deployment_mutations, 0);
  assert.equal(report.control_plane_llm_calls, 0);
  assert.equal(report.operations_llm_calls, 0);
  assert.equal(report.real_time_waits, 0);
  assert.equal(report.macos_launchd_dependency, false);
  assert.match(report.rehearsal_digest, /^[0-9a-f]{64}$/);
});

test("P0 rehearsal failure discards only staging and keeps current unchanged", () => {
  const steps = copy(FROZEN_DRESS_REHEARSAL_STEPS);
  steps[8] = {
    ...steps[8],
    status: "p0_failed",
    p0_reason: "operator_contract_or_rehearsal_failure",
  };

  const report = buildCleanStagingRehearsal({ steps });

  assert.equal(report.status, "failed");
  assert.equal(report.decision, "discard_staging_keep_current");
  assert.equal(report.go_no_go.local_rehearsal, "no_go");
  assert.equal(report.go_no_go.rollback, "discard_staging_keep_current");
  assert.equal(report.go_no_go.p0_failure_count, 1);
  assert.equal(report.staging.current_switch, false);
  assert.equal(report.deployment_mutations, 0);
});

test("unknown steps, hidden prerequisites and nonzero runtime effects fail closed", () => {
  const unknown = copy(FROZEN_DRESS_REHEARSAL_STEPS);
  unknown[0].id = "unknown_step";
  assert.throws(
    () => buildCleanStagingRehearsal({ steps: unknown }),
    (caught) => caught instanceof DressRehearsalError && caught.code === "DRESS_REHEARSAL_STEP_SET_INVALID",
  );

  const hidden = copy(FROZEN_DRESS_REHEARSAL_STEPS);
  hidden[0].undocumented_prerequisites = 1;
  assert.throws(
    () => buildCleanStagingRehearsal({ steps: hidden }),
    (caught) => caught instanceof DressRehearsalError && caught.code === "DRESS_REHEARSAL_OPERATOR_BOUNDARY_INVALID",
  );

  const networked = copy(FROZEN_DRESS_REHEARSAL_STEPS);
  networked[0].network_or_provider_operations = 1;
  assert.throws(
    () => buildCleanStagingRehearsal({ steps: networked }),
    (caught) => caught instanceof DressRehearsalError && caught.code === "DRESS_REHEARSAL_RUNTIME_BOUNDARY_INVALID",
  );
});

test("activation plan is contract-only and identifies every authority boundary", () => {
  const plan = buildActivationPlan();

  assert.equal(plan.mode, "operator_contract_only_no_external_execution");
  assert.equal(plan.real_execution, "activation_pending");
  assert.equal(plan.current_unchanged_until_authorized_switch, true);
  assert.equal(plan.copy_safe_local_steps, 6);
  assert.equal(plan.external_authority_required_for.length, 9);
  assert.equal(plan.ordered_steps.includes("execute_authorized_request_count_canary"), true);
  assert.match(plan.activation_plan_digest, /^[0-9a-f]{64}$/);
});

test("rehearsal evaluator and CLI contain no browser persistence, waits, network or platform activation", () => {
  const evaluator = fs.readFileSync(
    path.resolve(__dirname, "../src/services/release/canonical-dress-rehearsal.js"),
    "utf8",
  ).toLowerCase();
  const cli = fs.readFileSync(
    path.resolve(__dirname, "../scripts/dress-rehearsal-suite.js"),
    "utf8",
  ).toLowerCase();

  for (const marker of [
    "settimeout(",
    "setinterval(",
    "sleep(",
    "fetch(",
    "https.request",
    "http.request",
    "websocket",
    "launchctl",
    "launchdaemon",
    "com.apple.launchd",
    "systemctl",
    "child_process",
  ]) {
    assert.equal(evaluator.includes(marker), false, marker);
    assert.equal(cli.includes(marker), false, marker);
  }
});
