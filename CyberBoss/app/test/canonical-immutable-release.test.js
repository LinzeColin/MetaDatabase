"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  CB410_CLOSURE,
  CB420_CLOSURE,
  CB430_CLOSURE,
  FROZEN_CANARY_RECEIPTS,
  FROZEN_FEATURE_FLAGS,
  IMMUTABLE_RELEASE_SCHEMA,
  OPERATOR_RUNBOOK_SCHEMA,
  ImmutableReleaseError,
  assertFeatureFlags,
  buildImmutableReleaseCandidate,
  buildOperatorRunbook,
  evaluateRequestCountCanary,
} = require("../src/services/release/canonical-immutable-release");

function mutableCanaryReceipts() {
  return JSON.parse(JSON.stringify(FROZEN_CANARY_RECEIPTS));
}

test("immutable local candidate binds exact source, slots, flags, artifact digest, and request-count predicates", () => {
  const first = buildImmutableReleaseCandidate();
  const second = buildImmutableReleaseCandidate();
  assert.deepEqual(second, first);
  assert.equal(assertFeatureFlags(FROZEN_FEATURE_FLAGS), true);
  assert.equal(first.schema_version, IMMUTABLE_RELEASE_SCHEMA);
  assert.equal(first.product_version, "v0.0.0.5");
  assert.equal(first.status, "passed");
  assert.equal(first.release_decision, "candidate_local_only_not_promoted");
  assert.equal(first.source.source_commit, CB430_CLOSURE);
  assert.match(first.candidate_manifest_digest, /^[0-9a-f]{64}$/);
  assert.equal(first.source.remote_publication, "none");
  assert.equal(first.source.git_tag_created, false);
  assert.equal(first.slots.candidate.immutable, true);
  assert.equal(first.slots.candidate.current_switched, false);
  assert.equal(first.slots.current.release_id, CB420_CLOSURE);
  assert.equal(first.slots.previous.release_id, CB410_CLOSURE);
  assert.equal(first.slots.rollback.pointer, "previous");
  assert.equal(first.slots.rollback.valid, true);
  assert.equal(first.canary.request_count, 8);
  assert.equal(first.canary.read_only_request_count, 5);
  assert.equal(first.canary.p0_failures, 0);
  assert.equal(first.canary.current_unchanged, true);
  assert.equal(first.activation.candidate_installation, "activation_pending");
  assert.equal(first.activation.external_provider_operations, 0);
  assert.equal(first.activation.control_plane_llm_calls, 0);
  assert.equal(first.activation.operations_llm_calls, 0);
  assert.equal(first.activation.macos_launchd_dependency, false);
});

test("P0 request-count failure preserves current and requires immediate no-wait rollback", () => {
  const receipts = mutableCanaryReceipts();
  receipts[0].status = "p0_failed";
  const canary = evaluateRequestCountCanary(receipts);
  const report = buildImmutableReleaseCandidate({ canaryReceipts: receipts });
  assert.equal(canary.status, "failed");
  assert.equal(canary.p0_failures, 1);
  assert.equal(canary.rollback, "immediate_pointer_restore_no_wait");
  assert.equal(canary.current_unchanged, true);
  assert.equal(report.status, "failed");
  assert.equal(report.release_decision, "discard_candidate_keep_current");
  assert.equal(report.slots.rollback.target_release_id, CB410_CLOSURE);
});

test("feature scope and canary side effects fail closed", () => {
  const flags = JSON.parse(JSON.stringify(FROZEN_FEATURE_FLAGS));
  flags.enabled.push("CB_AUTONOMOUS_MUTATION");
  assert.throws(
    () => buildImmutableReleaseCandidate({ featureFlags: flags }),
    (caught) => caught instanceof ImmutableReleaseError && caught.code === "RELEASE_FEATURE_FLAGS_OUT_OF_SCOPE",
  );

  const receipts = mutableCanaryReceipts();
  receipts[0].network_or_provider_operations = 1;
  assert.throws(
    () => evaluateRequestCountCanary(receipts),
    (caught) => caught instanceof ImmutableReleaseError && caught.code === "RELEASE_CANARY_SIDE_EFFECT_FORBIDDEN",
  );
});

test("operator runbook is a no-live-execution contract", () => {
  const runbook = buildOperatorRunbook();
  assert.equal(runbook.schema_version, OPERATOR_RUNBOOK_SCHEMA);
  assert.equal(runbook.mode, "contract_only_no_live_execution");
  assert.equal(runbook.command_count, 8);
  assert.equal(runbook.prerequisites.fixed_sleep_allowed, false);
  assert.equal(runbook.external_execution, "activation_pending");
  assert.equal(runbook.real_time_waits, 0);
  assert.equal(runbook.network_or_provider_operations, 0);
  assert.equal(runbook.deployment_mutations, 0);
  assert.equal(runbook.control_plane_llm_calls, 0);
  assert.equal(runbook.operations_llm_calls, 0);
  assert.equal(runbook.macos_launchd_dependency, false);
  assert.match(runbook.runbook_digest, /^[0-9a-f]{64}$/);
});
