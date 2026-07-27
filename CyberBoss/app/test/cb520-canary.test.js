"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const {
  MAX_INPUT_BYTES,
  evaluatePolicyCanary,
  runReleaseCodeCanary,
} = require("../scripts/cb520-canary");

test("CB-520 release-code canary covers accepted, rejected and oversize policy paths", () => {
  assert.deepEqual(evaluatePolicyCanary(), {
    accepted_read_only: true,
    unauthorized_rejected: true,
    oversize_rejected: true,
    max_input_bytes: MAX_INPUT_BYTES,
  });
});

test("CB-520 release-code canary validates /stop semantics without a runtime turn", async () => {
  const receipt = await runReleaseCodeCanary();
  assert.equal(receipt.task_id, "CB-520");
  assert.equal(receipt.stop.stop_handler_cancelled_bound_turn, true);
  assert.equal(receipt.stop.runtime_turn_start_calls, 0);
  assert.equal(receipt.stop.control_plane_llm_calls, 0);
  assert.equal(receipt.stop.operations_llm_calls, 0);
  assert.equal(receipt.stop.real_wechat_delivery, "pending_missing_real_wechat_credential");
  assert.equal(receipt.real_time_waits, 0);
  assert.equal(receipt.simulator_started, false);
});

test("CB-520 release-code canary CLI emits a redacted machine-readable receipt", () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, "../scripts/cb520-canary.js")], {
    cwd: path.join(__dirname, ".."),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const receipt = JSON.parse(result.stdout.split("\n")[0]);
  assert.equal(receipt.schema_version, "cyberboss.cb520.release-code-canary.v1");
  assert.match(result.stdout, /CB520_RELEASE_CODE_CANARY=PASS/);
  assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_\b|\bsk-/i);
});
