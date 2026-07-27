const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const projectRoot = path.resolve(__dirname, "..");

test("model safety evaluation CLI emits a redacted fixture-only scorecard and pending real trial state", () => {
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-model-safety-evaluation.js",
    "evaluate",
    "--mode=fixture",
  ], { cwd: projectRoot, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const scorecard = JSON.parse(result.stdout.split("\n")[0]);
  assert.equal(scorecard.status, "passed");
  assert.equal(scorecard.evaluation_mode, "deterministic_fixture_only");
  assert.equal(scorecard.real_codex_trial_state, "activation_pending");
  assert.equal(scorecard.real_model_calls, 0);
  assert.equal(scorecard.secret_exfiltration_count, 0);
  assert.equal(scorecard.false_success_release_count, 0);
  assert.equal(scorecard.release_recommendation, "keep_release_disabled_pending_real_codex_trials");
  assert.match(result.stdout, /MODEL_SAFETY_EVALUATION=PASS/);
  assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|\/Users\//i);
});

test("model safety evaluation CLI rejects all real model trial requests", () => {
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-model-safety-evaluation.js",
    "evaluate",
    "--mode=real",
  ], { cwd: projectRoot, encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /MODEL_SAFETY_REAL_TRIAL_DISABLED/);
});
