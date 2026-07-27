const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const {
  CanonicalBackupError,
  createOnlineBackup,
  readBackupBundle,
  restoreBackupIsolated,
  simulateRemoteUpload,
  validateBackupScope,
} = require("../src/services/backup/canonical-backup-runtime");

const SOURCE_COMMIT = "a".repeat(40);
const CREATED_AT = "2026-07-27T03:20:00.000Z";

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-canonical-backup-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function scopePolicy() {
  return JSON.parse(fs.readFileSync(path.resolve(
    __dirname,
    "../../docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
  ), "utf8"));
}

function createRuntimeDatabase(filePath, { privateValue = "redacted-event" } = {}) {
  const database = new DatabaseSync(filePath);
  try {
    database.exec([
      "CREATE TABLE schema_migrations (version INTEGER NOT NULL)",
      "INSERT INTO schema_migrations (version) VALUES (5)",
      "CREATE TABLE runtime_events (id INTEGER PRIMARY KEY, category TEXT NOT NULL, payload TEXT NOT NULL)",
      "INSERT INTO runtime_events (category, payload) VALUES ('job', 'first-event')",
      "INSERT INTO runtime_events (category, payload) VALUES ('status', 'second-event')",
      `INSERT INTO runtime_events (category, payload) VALUES ('private', ${sqlText(privateValue)})`,
    ].join(";"));
  } finally {
    database.close();
  }
}

function insertRuntimeEvent(filePath, payload) {
  const database = new DatabaseSync(filePath);
  try {
    database.prepare("INSERT INTO runtime_events (category, payload) VALUES ('write-boundary', ?)").run(payload);
  } finally {
    database.close();
  }
}

function sqlText(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

test("online snapshot has a consistent concurrent-write boundary and isolated logical restore", (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "runtime.sqlite3");
  const output = path.join(root, "backups");
  createRuntimeDatabase(source);

  const backup = createOnlineBackup({
    sourceDbPath: source,
    outputDir: output,
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
    configReferences: ["runtime-db-ref", "identity-scope-ref"],
    beforeSerialize: () => insertRuntimeEvent(source, "included-before-serialize"),
    afterSerialize: () => insertRuntimeEvent(source, "excluded-after-serialize"),
  });
  const sourceDescription = describeRuntimeDatabase(source);
  const restored = restoreBackupIsolated({
    bundlePath: backup.bundlePath,
    restoreRoot: path.join(root, "isolated-restores"),
    networkDisabled: true,
  });

  assert.equal(backup.reused, false);
  assert.equal(backup.manifest.sqlite.sqlite_integrity, "ok");
  assert.equal(backup.manifest.sqlite.schema_version, 5);
  assert.equal(backup.manifest.sqlite.table_counts.runtime_events, 4);
  assert.equal(sourceDescription.runtimeEvents, 5);
  assert.deepEqual(backup.manifest.config_references, ["identity-scope-ref", "runtime-db-ref"]);
  assert.equal(backup.manifest.remote.r2.state, "activation_pending");
  assert.equal(backup.manifest.remote.oci.state, "activation_pending");
  assert.deepEqual(backup.manifest.counters, {
    real_r2_operations: 0,
    real_oci_operations: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    macos_launchd_dependency: false,
  });
  assert.equal(restored.status, "passed");
  assert.equal(restored.logical_digest, backup.manifest.sqlite.logical_digest);
  assert.equal(restored.network_disabled, true);
  assert.equal(restored.promoted, false);
  assert.equal(fs.readdirSync(path.join(root, "isolated-restores")).length, 0);
});

test("R2 and OCI local simulators keep exact frozen prefixes, hashes, and non-real receipts", (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "runtime.sqlite3");
  createRuntimeDatabase(source);
  const policy = scopePolicy();
  const backup = createOnlineBackup({
    sourceDbPath: source,
    outputDir: path.join(root, "backups"),
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: policy,
  });
  const r2 = simulateRemoteUpload({
    bundlePath: backup.bundlePath,
    provider: "r2",
    simulatorRoot: path.join(root, "r2-simulator"),
    scopePolicy: policy,
  });
  const oci = simulateRemoteUpload({
    bundlePath: backup.bundlePath,
    provider: "oci",
    simulatorRoot: path.join(root, "oci-simulator"),
    scopePolicy: policy,
  });

  assert.equal(r2.state, "simulator_verified");
  assert.equal(r2.bucket, "cyberboss-cold");
  assert.match(r2.object_key, /^ovh-singapore-vps-1\/snapshots\/backup_[a-f0-9]{24}\/runtime\.sqlite3$/);
  assert.equal(r2.real_remote_receipt, false);
  assert.equal(r2.real_provider_operations, 0);
  assert.equal(oci.state, "simulator_verified");
  assert.equal(oci.bucket, null);
  assert.equal(oci.bucket_reference, "oci-bucket-name");
  assert.match(oci.object_key, /^cyberboss-cold-backup\/ovh-singapore-vps-1\/snapshots\/backup_[a-f0-9]{24}\/runtime\.sqlite3$/);
  assert.equal(oci.real_remote_receipt, false);
  assert.equal(oci.real_provider_operations, 0);

  const r2Object = path.join(root, "r2-simulator", "r2", r2.bucket, r2.object_key);
  fs.writeFileSync(r2Object, "collision", "utf8");
  assert.throws(
    () => simulateRemoteUpload({
      bundlePath: backup.bundlePath,
      provider: "r2",
      simulatorRoot: path.join(root, "r2-simulator"),
      scopePolicy: policy,
    }),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_OBJECT_COLLISION",
  );
});

test("crash boundaries, archive tampering, and restore network policy fail closed", (t) => {
  const root = temporaryRoot(t);
  const source = path.join(root, "runtime.sqlite3");
  const output = path.join(root, "backups");
  createRuntimeDatabase(source);
  const common = {
    sourceDbPath: source,
    outputDir: output,
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
  };

  assert.throws(
    () => createOnlineBackup({ ...common, crashPoint: "before_publish" }),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_CRASH_BEFORE_PUBLISH",
  );
  assert.deepEqual(fs.readdirSync(output), []);

  assert.throws(
    () => createOnlineBackup({ ...common, crashPoint: "after_publish_before_dirsync" }),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_CRASH_AFTER_PUBLISH",
  );
  const bundlePath = path.join(output, fs.readdirSync(output).find((name) => name.startsWith("backup_")));
  const complete = readBackupBundle(bundlePath);
  assert.equal(complete.manifest.sqlite.sqlite_integrity, "ok");
  assert.throws(
    () => restoreBackupIsolated({ bundlePath, restoreRoot: root, networkDisabled: false }),
    (error) => error instanceof CanonicalBackupError && error.code === "RESTORE_NETWORK_MUST_BE_DISABLED",
  );
  fs.appendFileSync(path.join(bundlePath, "runtime.sqlite3"), "tamper", "utf8");
  assert.throws(
    () => readBackupBundle(bundlePath),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_ARCHIVE_HASH_MISMATCH",
  );
});

test("scope and privacy guard reject drift and a sensitive runtime image before publishing", (t) => {
  const root = temporaryRoot(t);
  const drifted = scopePolicy();
  drifted.cloudflare.r2.bucket = "wrong-bucket";
  assert.throws(
    () => validateBackupScope(drifted),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_SCOPE_POLICY_INVALID",
  );

  const source = path.join(root, "runtime.sqlite3");
  const syntheticPrivateMarker = ["-----BEGIN", "PRIVATE", "KEY-----"].join(" ");
  createRuntimeDatabase(source, { privateValue: syntheticPrivateMarker });
  const output = path.join(root, "backups");
  assert.throws(
    () => createOnlineBackup({
      sourceDbPath: source,
      outputDir: output,
      sourceCommit: SOURCE_COMMIT,
      createdAt: CREATED_AT,
      scopePolicy: scopePolicy(),
    }),
    (error) => error instanceof CanonicalBackupError && error.code === "BACKUP_PRIVACY_VIOLATION",
  );
  assert.deepEqual(fs.readdirSync(output), []);
});

function describeRuntimeDatabase(filePath) {
  const database = new DatabaseSync(filePath, { readOnly: true });
  try {
    return {
      runtimeEvents: Number(database.prepare("SELECT COUNT(*) AS count FROM runtime_events").get().count),
    };
  } finally {
    database.close();
  }
}
