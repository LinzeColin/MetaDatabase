const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const SOURCE_COMMIT = "b".repeat(40);
const CREATED_AT = "2026-07-27T03:21:00.000Z";

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-backup-cli-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function createRuntimeDatabase(filePath) {
  const database = new DatabaseSync(filePath);
  try {
    database.exec([
      "CREATE TABLE schema_migrations (version INTEGER NOT NULL)",
      "INSERT INTO schema_migrations (version) VALUES (5)",
      "CREATE TABLE runtime_events (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
      "INSERT INTO runtime_events (payload) VALUES ('event-one')",
    ].join(";"));
  } finally {
    database.close();
  }
}

test("canonical backup runtime CLI creates local snapshots and local-only R2/OCI simulator receipts", (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "runtime.sqlite3");
  const output = path.join(root, "backups");
  const r2Simulator = path.join(root, "r2-simulator");
  const ociSimulator = path.join(root, "oci-simulator");
  const restoreRoot = path.join(root, "restores");
  const policy = path.resolve(
    __dirname,
    "../docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
  );
  createRuntimeDatabase(source);

  const backup = spawnSync(process.execPath, [
    "app/scripts/canonical-backup-runtime.js", "backup",
    "--policy", policy,
    "--source-db", source,
    "--output-dir", output,
    "--source-commit", SOURCE_COMMIT,
    "--created-at", CREATED_AT,
    "--config-reference", "runtime-db-ref",
    "--r2-simulator-root", r2Simulator,
    "--oci-simulator-root", ociSimulator,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(backup.status, 0, backup.stderr);
  const receipt = JSON.parse(backup.stdout);
  assert.equal(receipt.status, "local_verified");
  assert.equal(receipt.sqlite_integrity, "ok");
  assert.equal(receipt.r2_state, "simulator_verified");
  assert.equal(receipt.oci_state, "simulator_verified");
  assert.equal(receipt.real_r2_operations, 0);
  assert.equal(receipt.real_oci_operations, 0);
  assert.equal(receipt.control_plane_llm_calls, 0);
  assert.equal(receipt.operations_llm_calls, 0);
  assert.doesNotMatch(backup.stdout, /-----BEGIN|Bearer\s+|\bgh[pousr]_|\bsk-|\/Users\//i);

  const bundleName = fs.readdirSync(output).find((name) => name.startsWith("backup_"));
  assert.ok(bundleName);
  const restored = spawnSync(process.execPath, [
    "app/scripts/canonical-backup-runtime.js", "restore",
    "--bundle", path.join(output, bundleName),
    "--restore-root", restoreRoot,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(restored.status, 0, restored.stderr);
  const restoreReceipt = JSON.parse(restored.stdout);
  assert.equal(restoreReceipt.status, "passed");
  assert.equal(restoreReceipt.network_disabled, true);
  assert.equal(restoreReceipt.promoted, false);
  assert.equal(restoreReceipt.real_provider_operations, 0);
});

test("canonical backup runtime CLI rejects incomplete input without writing a backup", (t) => {
  const root = temporaryRoot(t);
  const output = path.join(root, "backups");
  const result = spawnSync(process.execPath, [
    "app/scripts/canonical-backup-runtime.js", "backup",
    "--output-dir", output,
  ], { cwd: path.resolve(__dirname, ".."), encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(fs.existsSync(output), false);
  assert.match(result.stderr, /BACKUP_ARGUMENT_REQUIRED/);
});
