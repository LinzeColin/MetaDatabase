const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-access-cli-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

test("canonical Access plan CLI creates an atomic redacted domain plan without provider operations", (t) => {
  const root = temporaryRoot(t);
  const output = path.join(root, "access-plan.json");
  const policy = path.resolve(
    __dirname,
    "../docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
  );
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-access-plan.js", "plan",
    "--policy", policy,
    "--audience-reference", "access-audience-slot",
    "--issuer-reference", "access-issuer-slot",
    "--keyset-reference", "access-jwks-slot",
    "--output", output,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const receipt = JSON.parse(result.stdout);
  const plan = JSON.parse(fs.readFileSync(output, "utf8"));
  assert.equal(receipt.status, "planned");
  assert.equal(receipt.real_cloudflare_operations, 0);
  assert.equal(receipt.control_plane_llm_calls, 0);
  assert.equal(receipt.operations_llm_calls, 0);
  assert.equal(plan.hostname, "cyberboss.linzezhang.com");
  assert.equal(plan.access.default_action, "deny");
  assert.equal(plan.origin.access_jwt_required, true);
  assert.equal(plan.runtime.codex_listener, "ws://127.0.0.1:8765");
  assert.equal(plan.runtime.public_runtime_listener_allowed, false);
  assert.equal(plan.activation.dns_route, "activation_pending");
  assert.equal(plan.analytics.second_analytics_database_allowed, false);
  assert.doesNotMatch(`${result.stdout}\n${JSON.stringify(plan)}`, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|@|\/var\//i);
});

test("canonical Access plan CLI rejects incomplete inputs without writing a plan", (t) => {
  const root = temporaryRoot(t);
  const output = path.join(root, "access-plan.json");
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-access-plan.js", "plan",
    "--policy", "missing.json",
    "--output", output,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(fs.existsSync(output), false);
  assert.match(result.stderr, /ACCESS_ARGUMENT_REQUIRED/);
});
