const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const projectRoot = path.resolve(__dirname, "..");

test("fault recovery CLI emits a local deterministic matrix and nonblocking postdeploy plan", () => {
  for (const mode of ["matrix", "postdeploy-plan"]) {
    const result = spawnSync(process.execPath, [
      "app/scripts/fault-recovery-suite.js",
      "evaluate",
      `--mode=${mode}`,
    ], { cwd: projectRoot, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    const receipt = JSON.parse(result.stdout.split("\n")[0]);
    const counters = receipt.aggregate || receipt;
    assert.equal(receipt.status, "passed");
    assert.equal(receipt.product_version, "v0.0.0.5");
    assert.equal(receipt.taskpack_version, "v0.0.0.7");
    assert.equal(counters.network_or_provider_operations, 0);
    assert.equal(counters.control_plane_llm_calls, 0);
    assert.equal(counters.operations_llm_calls, 0);
    assert.equal(counters.macos_launchd_dependency, false);
    assert.match(result.stdout, /FAULT_RECOVERY_MATRIX=PASS/);
    assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_ |\bsk-|\/Users\//i);
  }
});

test("fault recovery CLI rejects real execution", () => {
  const result = spawnSync(process.execPath, [
    "app/scripts/fault-recovery-suite.js",
    "evaluate",
    "--mode=real",
  ], { cwd: projectRoot, encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /FAULT_RECOVERY_REAL_EXECUTION_DISABLED/);
});
