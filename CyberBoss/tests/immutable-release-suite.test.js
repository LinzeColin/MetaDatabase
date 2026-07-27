const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const projectRoot = path.resolve(__dirname, "..");

test("immutable release CLI emits local candidate and operator contract without activation", () => {
  for (const mode of ["local", "operator-plan"]) {
    const result = spawnSync(process.execPath, [
      "app/scripts/immutable-release-suite.js",
      "evaluate",
      `--mode=${mode}`,
    ], { cwd: projectRoot, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    const receipt = JSON.parse(result.stdout.split("\n")[0]);
    const counters = receipt.activation || receipt;
    assert.equal(receipt.product_version, "v0.0.0.5");
    assert.equal(receipt.taskpack_version, "v0.0.0.7");
    assert.equal(counters.network_or_provider_operations ?? counters.external_provider_operations, 0);
    assert.equal(counters.deployment_mutations, 0);
    assert.equal(counters.control_plane_llm_calls, 0);
    assert.equal(counters.operations_llm_calls, 0);
    assert.equal(counters.macos_launchd_dependency, false);
    assert.match(result.stdout, /IMMUTABLE_RELEASE_CANDIDATE=PASS/);
    assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|\/Users\//i);
  }
});

test("immutable release CLI rejects live activation, canary, and rollback", () => {
  for (const mode of ["activate", "canary-live", "rollback-live"]) {
    const result = spawnSync(process.execPath, [
      "app/scripts/immutable-release-suite.js",
      "evaluate",
      `--mode=${mode}`,
    ], { cwd: projectRoot, encoding: "utf8" });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /IMMUTABLE_RELEASE_EXTERNAL_EXECUTION_DISABLED/);
  }
});
