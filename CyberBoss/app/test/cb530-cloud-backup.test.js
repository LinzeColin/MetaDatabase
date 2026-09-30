"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const {
  CloudBackupError,
  buildOciObjectUrl,
  buildR2ObjectUrl,
  bootstrapRuntimeDatabase,
  readOptionalCredentialFile,
  restoreRemoteBackup,
  runCloudBackup,
} = require("../src/services/backup/cb530-cloud-backup");
const { backupRequest } = require("../scripts/cb530-cloud-backup");
const { R2ObjectClient } = require("../src/services/backup/object-clients");

const SOURCE_COMMIT = "b".repeat(40);
const CREATED_AT = "2026-07-27T12:00:00.000Z";
const ACCOUNT_ID = "a".repeat(32);
const TOKEN = "token-value-for-cb530-testing-1234567890";
const PAR = "https://objectstorage.example.invalid/p/redacted/n/example/b/backup/o/";

function temporaryRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb530-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function scopePolicy() {
  return {
    schema_version: 1,
    cloudflare: { r2: { bucket: "cyberboss-cold", object_prefix: "ovh-singapore-vps-1/", public_access: false } },
    oci: { bucket_slot: "oci-bucket-name", object_prefix: "cyberboss-cold-backup/ovh-singapore-vps-1/", public_access: false },
  };
}

function createRuntimeDatabase(filePath) {
  const database = new DatabaseSync(filePath);
  try {
    database.exec([
      "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, source_commit TEXT NOT NULL);",
      "INSERT INTO schema_migrations VALUES (1, '2026-07-27T12:00:00.000Z', 'fixture');",
      "CREATE TABLE runtime_events (id TEXT PRIMARY KEY, detail TEXT NOT NULL);",
      "INSERT INTO runtime_events VALUES ('event-1', 'bounded-maintenance');",
    ].join("\n"));
  } finally {
    database.close();
  }
}

function fakeProvider({ ociReadable = true, ociPutStatus = null, requestLog = null } = {}) {
  const r2 = new Map();
  const oci = new Map();
  return async (input, init = {}) => {
    const url = new URL(String(input));
    if (requestLog) {
      requestLog.push(url.hostname);
    }
    const method = String(init.method || "GET").toUpperCase();
    if (url.pathname.includes("/r2/buckets/cyberboss-cold/objects/")) {
      const key = decodeURIComponent(url.pathname.split("/objects/", 2)[1]);
      if (method === "GET") {
        return r2.has(key) ? new Response(r2.get(key), { status: 200, headers: { etag: "r2" } }) : new Response("missing", { status: 404 });
      }
      if (method === "PUT") {
        assert.equal(init.headers["cf-r2-storage-class"], "Standard");
        if (r2.has(key)) {
          return new Response("exists", { status: 409 });
        }
        r2.set(key, Buffer.from(init.body));
        return new Response(null, { status: 200, headers: { etag: "r2" } });
      }
    }
    if (url.hostname === "objectstorage.example.invalid") {
      const key = decodeURIComponent(url.pathname.split("/o/", 2)[1]);
      if (method === "PUT") {
        if (ociPutStatus !== null) {
          return new Response("provider-down", { status: ociPutStatus });
        }
        if (oci.has(key)) {
          return new Response("exists", { status: 412 });
        }
        oci.set(key, Buffer.from(init.body));
        return new Response(null, { status: 201, headers: { etag: "oci" } });
      }
      if (method === "GET") {
        if (!ociReadable) {
          return new Response("write-only", { status: 403 });
        }
        return oci.has(key) ? new Response(oci.get(key), { status: 200, headers: { etag: "oci" } }) : new Response("missing", { status: 404 });
      }
    }
    return new Response("unexpected", { status: 500 });
  };
}

test("R2 S3 writer signs an explicit Standard storage class", async () => {
  let requestHeaders;
  const client = new R2ObjectClient({
    accountId: ACCOUNT_ID,
    bucket: "cyberboss-cold",
    accessKeyId: "fixture-access-key",
    secretAccessKey: "fixture-secret-key",
    now: () => new Date(CREATED_AT),
    fetchImpl: async (_url, init) => {
      requestHeaders = init.headers;
      return new Response(null, { status: 200, headers: { "x-amz-version-id": "fixture-version" } });
    },
  });
  await client.putObject({ key: "backup/fixture.bin", body: Buffer.from("fixture") });
  assert.equal(requestHeaders["x-amz-storage-class"], "STANDARD");
});

test("CB-530 real-provider protocol keeps frozen object scopes and restores the R2 readback in isolation", async (t) => {
  const root = temporaryRoot(t);
  const databasePath = path.join(root, "runtime.sqlite3");
  createRuntimeDatabase(databasePath);
  const result = await runCloudBackup({
    sourceDbPath: databasePath,
    outputDir: path.join(root, "snapshots"),
    restoreRoot: path.join(root, "restore"),
    receiptDir: path.join(root, "receipts"),
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
    r2AccountId: ACCOUNT_ID,
    r2Token: TOKEN,
    ociParUrl: PAR,
    fetchImpl: fakeProvider(),
  });
  assert.equal(result.status, "passed");
  assert.equal(result.r2.state, "verified");
  assert.equal(result.r2.readback_verified, true);
  assert.equal(result.r2.provider_requests, 6);
  assert.equal(result.oci.state, "verified");
  assert.equal(result.oci.provider_requests, 3);
  assert.equal(result.isolated_restore.status, "passed");
  assert.equal(result.isolated_restore.network_disabled, true);
  assert.equal(result.isolated_restore.promoted, false);
  assert.equal(result.counters.control_plane_llm_calls, 0);
  assert.equal(result.counters.operations_llm_calls, 0);
  assert.equal(fs.existsSync(result.receipt_path), true);
});

test("CB-530 accepts a write-only OCI PAR as explicit readback-pending without weakening R2 recovery", async (t) => {
  const root = temporaryRoot(t);
  const databasePath = path.join(root, "runtime.sqlite3");
  createRuntimeDatabase(databasePath);
  const result = await runCloudBackup({
    sourceDbPath: databasePath,
    outputDir: path.join(root, "snapshots"),
    restoreRoot: path.join(root, "restore"),
    receiptDir: path.join(root, "receipts"),
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
    r2AccountId: ACCOUNT_ID,
    r2Token: TOKEN,
    ociParUrl: PAR,
    fetchImpl: fakeProvider({ ociReadable: false }),
  });
  assert.equal(result.r2.state, "verified");
  assert.equal(result.oci.state, "write_verified_read_pending");
  assert.equal(result.oci.readback_state, "activation_pending_write_only_par");
  assert.equal(result.isolated_restore.status, "passed");
});

test("CB-530 rejects scope drift and supports a separate exact R2 restore command", async (t) => {
  const root = temporaryRoot(t);
  const databasePath = path.join(root, "runtime.sqlite3");
  createRuntimeDatabase(databasePath);
  const provider = fakeProvider();
  const backup = await runCloudBackup({
    sourceDbPath: databasePath,
    outputDir: path.join(root, "snapshots"),
    restoreRoot: path.join(root, "restore"),
    receiptDir: path.join(root, "receipts"),
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
    r2AccountId: ACCOUNT_ID,
    r2Token: TOKEN,
    ociParUrl: PAR,
    fetchImpl: provider,
  });
  const restored = await restoreRemoteBackup({
    backupId: backup.backup_id,
    restoreRoot: path.join(root, "restore-second"),
    r2AccountId: ACCOUNT_ID,
    r2Token: TOKEN,
    fetchImpl: provider,
  });
  assert.equal(restored.status, "passed");
  assert.equal(restored.r2_provider_requests, 2);
  assert.throws(
    () => buildR2ObjectUrl(ACCOUNT_ID, "other-prefix/backup_aaaaaaaaaaaaaaaaaaaaaaaa/runtime.sqlite3"),
    (error) => error instanceof CloudBackupError && error.code === "CB530_R2_OBJECT_SCOPE_INVALID",
  );
  assert.throws(
    () => buildOciObjectUrl(PAR, "cyberboss-cold-backup/other/backup_aaaaaaaaaaaaaaaaaaaaaaaa/runtime.sqlite3"),
    (error) => error instanceof CloudBackupError && error.code === "CB530_OCI_OBJECT_SCOPE_INVALID",
  );
});

test("CB-530 bootstrap creates only the frozen Runtime spool schema", (t) => {
  const root = temporaryRoot(t);
  const schemaPath = path.join(root, "runtime-spool.sql");
  const databasePath = path.join(root, "runtime.db");
  fs.writeFileSync(schemaPath, "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, source_commit TEXT NOT NULL); INSERT INTO schema_migrations VALUES (1, 'fixture', 'fixture');", "utf8");
  assert.deepEqual(bootstrapRuntimeDatabase({ sourceDbPath: databasePath, schemaPath }), { created: true });
  assert.deepEqual(bootstrapRuntimeDatabase({ sourceDbPath: databasePath, schemaPath }), { created: false });
  const database = new DatabaseSync(databasePath, { readOnly: true });
  try {
    assert.equal(database.prepare("PRAGMA integrity_check").get().integrity_check, "ok");
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM schema_migrations").get().count, 1);
  } finally {
    database.close();
  }
});

test("CB-530 CLI request preserves the managed Runtime source path", () => {
  const config = { sourceDb: "/var/lib/cyberboss/runtime.db", outputDir: "/var/lib/cyberboss/snapshots" };
  const request = backupRequest(config, SOURCE_COMMIT, CREATED_AT);
  assert.equal(request.sourceDbPath, config.sourceDb);
  assert.equal(request.sourceCommit, SOURCE_COMMIT);
  assert.equal(request.createdAt, CREATED_AT);
  assert.throws(
    () => backupRequest({}, SOURCE_COMMIT, CREATED_AT),
    (error) => error instanceof CloudBackupError && error.code === "CB530_RUNTIME_DB_PATH_INVALID",
  );
});

async function backupWith(t, overrides) {
  const root = temporaryRoot(t);
  const databasePath = path.join(root, "runtime.sqlite3");
  createRuntimeDatabase(databasePath);
  return runCloudBackup({
    sourceDbPath: databasePath,
    outputDir: path.join(root, "snapshots"),
    restoreRoot: path.join(root, "restore"),
    receiptDir: path.join(root, "receipts"),
    sourceCommit: SOURCE_COMMIT,
    createdAt: CREATED_AT,
    scopePolicy: scopePolicy(),
    r2AccountId: ACCOUNT_ID,
    r2Token: TOKEN,
    ...overrides,
  });
}

for (const [label, ociParUrl] of [["null", null], ["undefined", undefined], ["empty string", ""]]) {
  test(`CB-530 skips the OCI leg entirely when ociParUrl is ${label}: R2 alone is passed`, async (t) => {
    const requestLog = [];
    const result = await backupWith(t, { ociParUrl, fetchImpl: fakeProvider({ requestLog }) });
    assert.equal(requestLog.includes("objectstorage.example.invalid"), false);
    assert.equal(requestLog.length > 0, true);
    assert.equal(result.status, "passed");
    assert.equal(result.cold_copies_landed, 1);
    assert.equal(result.r2.state, "verified");
    assert.deepEqual({ ...result.oci }, { state: "disabled", reason: "OCI_NOT_CONFIGURED", provider_requests: 0 });
    assert.equal(Object.isFrozen(result.oci), true);
    assert.equal(result.counters.oci_provider_requests, 0);
    assert.equal(result.isolated_restore.status, "passed");
    const receipt = JSON.parse(fs.readFileSync(result.receipt_path, "utf8"));
    assert.equal(receipt.oci.state, "disabled");
    assert.equal(receipt.counters.oci_provider_requests, 0);
  });
}

test("CB-530 configured OCI that fails is still degraded (exit-0 result), R2 landed", async (t) => {
  const result = await backupWith(t, { ociParUrl: PAR, fetchImpl: fakeProvider({ ociPutStatus: 500 }) });
  assert.equal(result.status, "degraded");
  assert.equal(result.cold_copies_landed, 1);
  assert.equal(result.r2.state, "verified");
  assert.equal(result.oci.state, "failed");
  assert.equal(result.oci.error_code, "CB530_OCI_PUT_FAILED");
});

test("CB-530 with OCI configured and both legs landed reports passed with two copies", async (t) => {
  const result = await backupWith(t, { ociParUrl: PAR, fetchImpl: fakeProvider() });
  assert.equal(result.status, "passed");
  assert.equal(result.cold_copies_landed, 2);
});

test("CB-530 still fails when the only enabled leg (R2) fails and OCI is not configured", async (t) => {
  const failingR2 = async () => new Response("denied", { status: 403 });
  await assert.rejects(
    backupWith(t, { ociParUrl: null, fetchImpl: failingR2 }),
    (error) => error instanceof CloudBackupError && error.code === "CB530_R2_PRECHECK_FAILED",
  );
});

test("CB-530 optional OCI credential file: missing is null, present-but-empty/invalid fails closed", (t) => {
  const root = temporaryRoot(t);
  const code = "CB530_OCI_PAR_FILE_INVALID";
  assert.equal(readOptionalCredentialFile(path.join(root, "oci_par_url"), code), null);
  const empty = path.join(root, "empty");
  fs.writeFileSync(empty, "  \n", "utf8");
  assert.throws(() => readOptionalCredentialFile(empty, code), (e) => e instanceof CloudBackupError && e.code === code);
  const multiline = path.join(root, "multiline");
  fs.writeFileSync(multiline, "a\nb", "utf8");
  assert.throws(() => readOptionalCredentialFile(multiline, code), (e) => e instanceof CloudBackupError && e.code === code);
  const good = path.join(root, "good");
  fs.writeFileSync(good, `${PAR}\n`, "utf8");
  assert.equal(readOptionalCredentialFile(good, code), PAR);
  assert.throws(() => readOptionalCredentialFile("relative/path", code), (e) => e.code === code);
});
