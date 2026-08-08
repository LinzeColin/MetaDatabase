import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPublicDeployGates,
  evidenceReference,
  redactCommandResult,
} from "../scripts/verify-public-launch-preflight.mjs";

test("public deployment gates remain closed for current local-only evidence", () => {
  const gates = buildPublicDeployGates({
    assetManifest: {
      status: "PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED",
      raw: { public_release_policy: { current_state: "BLOCKED_ASSET_RIGHTS" } },
    },
    ownerActivation: { status: "BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK" },
    authSaved: { status: "NOT_RUN", savedCandidate: "NOT_RUN" },
    moduleMatrix: { raw: { checks: { second_device_sync: "not_run" } } },
  });

  assert.deepEqual(gates.map((gate) => gate.id), [
    "authorized_public_assets",
    "owner_activation",
    "saved_candidate_identity",
    "second_device_sync",
  ]);
  assert.equal(gates.every((gate) => gate.satisfied), false);
});

test("public deployment gates can only become satisfied with explicit external evidence", () => {
  const gates = buildPublicDeployGates({
    assetManifest: {
      status: "PASS_FINAL_AUTHORIZED_ASSETS",
      raw: { public_release_policy: { current_state: "APPROVED" } },
    },
    ownerActivation: { status: "PASS_LOCAL_OWNER_ACTIVATION_PRECHECK" },
    authSaved: { status: "PASS_SAVED_CANDIDATE_AUTH", savedCandidate: "PASS" },
    moduleMatrix: { raw: { checks: { second_device_sync: "pass" } } },
  });

  assert.equal(gates.every((gate) => gate.satisfied), true);
});

test("public launch evidence redacts raw evidence and command output", () => {
  const reference = evidenceReference(
    {
      exists: true,
      status: "PASS_LOCAL_CONTRACT",
      savedCandidate: "NOT_RUN",
      raw: { secret: "SENTINEL_EVIDENCE_SECRET" },
    },
    "13_evidence/auth.json",
  );
  const command = redactCommandResult({
    name: "test",
    command: "npm run test:s2",
    status: 0,
    signal: null,
    ok: true,
    stdout: "SENTINEL_COMMAND_OUTPUT",
    stderr: "SENTINEL_COMMAND_ERROR",
  });

  const serialized = JSON.stringify({ reference, command });
  assert.equal(serialized.includes("SENTINEL_"), false);
  assert.equal("raw" in reference, false);
  assert.equal("stdout" in command, false);
  assert.equal("stderr" in command, false);
});
