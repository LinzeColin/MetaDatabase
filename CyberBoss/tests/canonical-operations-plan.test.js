const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const NOW = "2026-07-27T03:20:00.000Z";

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-operations-cli-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function writeFixture(root, name, value) {
  const filePath = path.join(root, name);
  fs.writeFileSync(filePath, `${JSON.stringify(value)}\n`, "utf8");
  return filePath;
}

function snapshot() {
  return {
    poll: { lastSuccessAt: NOW },
    runtime: { ready: false },
    memory: { totalMb: 4096, availableMb: 3000 },
    storage: { usedPercent: 40, inodeUsedPercent: 10 },
    load: { oneMinute: 0.2, cpuCount: 2 },
    queue: { depth: 0, oldestQueuedAt: null, activeRuntime: false },
  };
}

function inventory() {
  return {
    local_backups: [],
    runtime_logs: [],
    diagnostic_summaries: [],
    build_cache_bytes: 0,
    spool_entries: 0,
  };
}

function retentionPolicy() {
  return {
    schema_version: "cyberboss.retention.v2",
    runtime_logs_days: 7,
    diagnostic_summaries_days: 30,
    local_verified_backups: 2,
    immutable_release_slots: ["current", "previous"],
    build_cache_max_bytes: 536870912,
    raw_private_messages_in_github: false,
    auth_cache_in_standard_backup: false,
    no_empty_canonical_commit: true,
  };
}

test("canonical operations plan CLI emits one local-only bounded self-heal policy", (t) => {
  const root = temporaryRoot(t);
  const policy = writeFixture(root, "retention-policy.json", retentionPolicy());
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-operations-plan.js", "plan",
    "--snapshot", writeFixture(root, "snapshot.json", snapshot()),
    "--retention-policy", policy,
    "--inventory", writeFixture(root, "inventory.json", inventory()),
    "--now", NOW,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const receipt = JSON.parse(result.stdout);
  assert.equal(receipt.status, "planned");
  assert.equal(receipt.guard_state, "protect");
  assert.equal(receipt.action, "try_restart_single_service");
  assert.equal(receipt.action_max_invocations, 1);
  assert.equal(receipt.timer_activation, "activation_pending");
  assert.equal(receipt.timer_installed, false);
  assert.equal(receipt.real_service_operations, 0);
  assert.equal(receipt.real_backup_operations, 0);
  assert.equal(receipt.control_plane_llm_calls, 0);
  assert.equal(receipt.operations_llm_calls, 0);
  assert.doesNotMatch(result.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|\/Users\//i);
});

test("canonical operations plan CLI rejects incomplete inputs without a hidden action", (t) => {
  const root = temporaryRoot(t);
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-operations-plan.js", "plan",
    "--snapshot", writeFixture(root, "snapshot.json", snapshot()),
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /OPERATIONS_ARGUMENT_REQUIRED/);
});
