const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const projectRoot = path.resolve(__dirname, "..");

test("security assurance CLI emits local deterministic report and never claims external activation", () => {
  const result = spawnSync(process.execPath, [
    "app/scripts/security-assurance-suite.js",
    "evaluate",
    "--mode=local",
  ], { cwd: projectRoot, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout.split("\n")[0]);
  assert.equal(report.status, "passed");
  assert.equal(report.evaluation_mode, "local_deterministic_read_only");
  assert.equal(report.security.high_confidence_secret_hits, 0);
  assert.equal(report.sbom.component_count, 129);
  assert.equal(report.corresponding_source.corresponding_source_complete, true);
  assert.equal(report.access_and_analytics_privacy.external_8765, "unreachable");
  assert.equal(report.external_activation.cloudflare_web_analytics, "activation_pending");
  assert.match(result.stdout, /SECURITY_ASSURANCE=PASS/);
  assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|\/Users\//i);
});

test("security assurance CLI rejects external release or provider execution modes", () => {
  const result = spawnSync(process.execPath, [
    "app/scripts/security-assurance-suite.js",
    "evaluate",
    "--mode=release",
  ], { cwd: projectRoot, encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /SECURITY_ASSURANCE_EXTERNAL_RELEASE_DISABLED/);
});
