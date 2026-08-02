"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const {
  CanonicalBackupError,
  OCI_PREFIX,
  R2_BUCKET,
  R2_PREFIX,
  createOnlineBackup,
  restoreBackupIsolated,
} = require("./canonical-backup-runtime");

const R2_API_ROOT = "https://api.cloudflare.com/client/v4";
const R2_SNAPSHOT_PREFIX = `${R2_PREFIX}snapshots/`;
const OCI_SNAPSHOT_PREFIX = `${OCI_PREFIX}snapshots/`;
const SNAPSHOT_FILENAMES = Object.freeze(["runtime.sqlite3", "manifest.json"]);
const MAX_OBJECT_BYTES = 64 * 1024 * 1024;

class CloudBackupError extends Error {
  constructor(code) {
    super(code);
    this.name = "CloudBackupError";
    this.code = code;
  }
}

function bootstrapRuntimeDatabase({ sourceDbPath, schemaPath } = {}) {
  const databasePath = requireAbsolutePath(sourceDbPath, "CB530_RUNTIME_DB_PATH_INVALID");
  const schema = readTextFile(schemaPath, "CB530_RUNTIME_SCHEMA_UNAVAILABLE");
  if (fs.existsSync(databasePath)) {
    assertRegularFile(databasePath, "CB530_RUNTIME_DB_INVALID");
    return Object.freeze({ created: false });
  }
  const parent = path.dirname(databasePath);
  fs.mkdirSync(parent, { recursive: true, mode: 0o750 });
  let database;
  try {
    database = new DatabaseSync(databasePath);
    database.exec(schema);
  } catch {
    throw new CloudBackupError("CB530_RUNTIME_BOOTSTRAP_FAILED");
  } finally {
    if (database) {
      database.close();
    }
  }
  try {
    fs.chmodSync(databasePath, 0o600);
    assertRegularFile(databasePath, "CB530_RUNTIME_DB_INVALID");
    const check = new DatabaseSync(databasePath, { readOnly: true });
    try {
      const result = check.prepare("PRAGMA integrity_check").get();
      if (String(result.integrity_check || "") !== "ok") {
        throw new CloudBackupError("CB530_RUNTIME_BOOTSTRAP_INTEGRITY_FAILED");
      }
    } finally {
      check.close();
    }
  } catch (error) {
    if (error instanceof CloudBackupError) {
      throw error;
    }
    throw new CloudBackupError("CB530_RUNTIME_BOOTSTRAP_FAILED");
  }
  return Object.freeze({ created: true });
}

async function runCloudBackup({
  sourceDbPath,
  outputDir,
  restoreRoot,
  receiptDir,
  sourceCommit,
  createdAt,
  scopePolicy,
  r2AccountId,
  r2Token,
  ociParUrl,
  fetchImpl = globalThis.fetch,
} = {}) {
  const source = requireAbsolutePath(sourceDbPath, "CB530_RUNTIME_DB_PATH_INVALID");
  const output = requireAbsolutePath(outputDir, "CB530_OUTPUT_PATH_INVALID");
  const restore = requireAbsolutePath(restoreRoot, "CB530_RESTORE_PATH_INVALID");
  const receipts = requireAbsolutePath(receiptDir || path.join(output, "receipts"), "CB530_RECEIPT_PATH_INVALID");
  assertRegularFile(source, "CB530_RUNTIME_DB_INVALID");
  assertFetch(fetchImpl);
  const backup = createOnlineBackup({
    sourceDbPath: source,
    outputDir: output,
    sourceCommit,
    createdAt,
    scopePolicy,
    configReferences: ["identity-scope-policy", "runtime-spool-schema"],
  });
  // 两份冷备各自独立地传，一份挂了不影响另一份。
  //
  // 原来是串着的：uploadR2Bundle 先跑，它一抛，uploadOciBundle 永远轮不到。
  // 于是 2026-08-01T23:53 起 R2 因为令牌没有写权限连续失败的那几天里，OCI 那
  // 一份**一次都没写过**——异地副本数从「两份」直接掉到「零份」，而不是「一份」。
  //
  // 那不是冗余，那是把两个单点串成了一条链：任何一边坏掉，整条备份就没了。
  // 双冷备的全部意义就是它们不该互相牵连。
  //
  // 所以两边各自兜住异常，各自如实记状态，最后只在**两份都失败**时才算这一轮
  // 失败。剩一份也是异地有副本——那和一份都没有是完全不同的处境，运维上要
  // 分得开：前者是「补一条腿」，后者是「现在就去手工备份」。
  const r2 = await attemptCopy("r2", () => uploadR2Bundle({
    bundle: backup,
    accountId: r2AccountId,
    token: r2Token,
    fetchImpl,
  }));
  // 隔离恢复只能从**读得回来的**那一份做。R2 挂了就没有 downloaded，
  // 这时候不是失败，是「这一轮没法做回读校验」，要说得出是为什么。
  const restored = r2.downloaded
    ? restoreDownloadedR2Bundle({
      backup,
      downloaded: r2.downloaded,
      restoreRoot: restore,
    })
    : Object.freeze({ state: "skipped", reason: "R2_COPY_UNAVAILABLE" });
  const oci = await attemptCopy("oci", () => uploadOciBundle({
    bundle: backup,
    parUrl: ociParUrl,
    fetchImpl,
  }));
  const landed = [r2, oci].filter((copy) => copy.state !== "failed");
  if (landed.length === 0) {
    // 两份都没落地：这一轮**确实**没有任何异地副本，必须失败。
    throw new CloudBackupError(r2.error_code || oci.error_code || "CB530_ALL_COLD_COPIES_FAILED");
  }
  const receipt = Object.freeze({
    schema_version: "cyberboss.cb530.provider-receipt.v1",
    product_version: "v0.0.0.5",
    backup_id: backup.manifest.backup_id,
    source_commit: backup.manifest.source_commit,
    archive_sha256: backup.manifest.archive.sha256,
    manifest_sha256: sha256File(backup.manifestPath),
    sqlite_integrity: backup.manifest.sqlite.sqlite_integrity,
    logical_digest: backup.manifest.sqlite.logical_digest,
    r2: withoutDownloaded(r2),
    oci,
    isolated_restore: restored,
    counters: {
      r2_provider_requests: r2.provider_requests,
      oci_provider_requests: oci.provider_requests,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    },
  });
  const receiptPath = path.join(receipts, `${backup.manifest.backup_id}.json`);
  writeJsonDurable(receiptPath, receipt);
  return Object.freeze({
    // 两份都落地才叫 passed。剩一份是 degraded——它**成功了**（异地确实有副本，
    // 所以退出码是 0、不该让 systemd 每晚报警），但它和「两份都在」不是一回事，
    // 运维要看得出来。挤成一个 passed 的话，双冷备退化成单冷备且无人知晓。
    status: landed.length === 2 ? "passed" : "degraded",
    cold_copies_landed: landed.length,
    backup_id: backup.manifest.backup_id,
    archive_sha256: backup.manifest.archive.sha256,
    manifest_sha256: sha256File(backup.manifestPath),
    sqlite_integrity: backup.manifest.sqlite.sqlite_integrity,
    logical_digest: backup.manifest.sqlite.logical_digest,
    r2: withoutDownloaded(r2),
    oci,
    isolated_restore: restored,
    receipt_sha256: sha256File(receiptPath),
    receipt_path: receiptPath,
    counters: receipt.counters,
  });
}

async function restoreRemoteBackup({
  backupId,
  restoreRoot,
  r2AccountId,
  r2Token,
  fetchImpl = globalThis.fetch,
} = {}) {
  const id = normalizeBackupId(backupId);
  const restore = requireAbsolutePath(restoreRoot, "CB530_RESTORE_PATH_INVALID");
  assertFetch(fetchImpl);
  const snapshot = await getR2Object({
    accountId: r2AccountId,
    token: r2Token,
    objectKey: r2ObjectKey(id, "runtime.sqlite3"),
    fetchImpl,
    expectedSha256: null,
  });
  const manifest = await getR2Object({
    accountId: r2AccountId,
    token: r2Token,
    objectKey: r2ObjectKey(id, "manifest.json"),
    fetchImpl,
    expectedSha256: null,
  });
  const temporaryRoot = fs.mkdtempSync(path.join(ensureDirectory(restore), ".cb530-r2-restore-"));
  try {
    const bundle = path.join(temporaryRoot, id);
    fs.mkdirSync(bundle, { mode: 0o700 });
    writeBufferDurable(path.join(bundle, "runtime.sqlite3"), snapshot.body);
    writeBufferDurable(path.join(bundle, "manifest.json"), manifest.body);
    const restored = restoreBackupIsolated({
      bundlePath: bundle,
      restoreRoot: restore,
      networkDisabled: true,
    });
    return Object.freeze({
      ...restored,
      backup_id: id,
      r2_provider_requests: 2,
      r2_readback_verified: true,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    });
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

// 一份冷备的尝试。挂了就如实记下来，不把另一份也带走。
//
// 只吞 CloudBackupError 这一类：别的异常（编程错误、越界）该炸出来，
// 被这里吞掉的话，一个真 bug 会伪装成「那家云今天不行」。
async function attemptCopy(label, run) {
  try {
    return await run();
  } catch (error) {
    if (!(error instanceof CloudBackupError)) {
      throw error;
    }
    return Object.freeze({
      state: "failed",
      error_code: error.code || `CB530_${label.toUpperCase()}_FAILED`,
      real_remote_receipt: false,
      provider_requests: 0,
      objects: Object.freeze([]),
    });
  }
}

async function uploadR2Bundle({ bundle, accountId, token, fetchImpl }) {
  const id = normalizeBackupId(bundle?.manifest?.backup_id);
  const items = [
    { filename: "runtime.sqlite3", sourcePath: bundle.snapshotPath, sha256: bundle.manifest.archive.sha256 },
    { filename: "manifest.json", sourcePath: bundle.manifestPath, sha256: sha256File(bundle.manifestPath) },
  ];
  const downloaded = {};
  const objectReceipts = [];
  for (const item of items) {
    const receipt = await putR2Object({
      accountId,
      token,
      objectKey: r2ObjectKey(id, item.filename),
      sourcePath: item.sourcePath,
      expectedSha256: item.sha256,
      fetchImpl,
    });
    downloaded[item.filename] = receipt.body;
    objectReceipts.push(withoutBody(receipt));
  }
  return Object.freeze({
    state: "verified",
    bucket: R2_BUCKET,
    prefix: R2_SNAPSHOT_PREFIX,
    backup_id: id,
    objects: objectReceipts,
    metadata_verified: true,
    readback_verified: true,
    real_remote_receipt: true,
    provider_requests: items.length * 3,
    downloaded: Object.freeze(downloaded),
  });
}

async function uploadOciBundle({ bundle, parUrl, fetchImpl }) {
  const id = normalizeBackupId(bundle?.manifest?.backup_id);
  const items = [
    { filename: "runtime.sqlite3", sourcePath: bundle.snapshotPath, sha256: bundle.manifest.archive.sha256 },
    { filename: "manifest.json", sourcePath: bundle.manifestPath, sha256: sha256File(bundle.manifestPath) },
  ];
  const objectReceipts = [];
  for (const item of items) {
    objectReceipts.push(await putOciObject({
      parUrl,
      objectKey: ociObjectKey(id, item.filename),
      sourcePath: item.sourcePath,
      expectedSha256: item.sha256,
      fetchImpl,
    }));
  }
  const readback = await readOciObjectIfAllowed({
    parUrl,
    objectKey: ociObjectKey(id, "runtime.sqlite3"),
    expectedSha256: bundle.manifest.archive.sha256,
    fetchImpl,
  });
  return Object.freeze({
    state: readback.verified ? "verified" : "write_verified_read_pending",
    bucket_reference: "oci-bucket-name",
    prefix: OCI_SNAPSHOT_PREFIX,
    backup_id: id,
    objects: objectReceipts,
    metadata_verified: true,
    readback_verified: readback.verified,
    readback_state: readback.state,
    real_remote_receipt: true,
    provider_requests: items.length + 1,
  });
}

async function putR2Object({ accountId, token, objectKey, sourcePath, expectedSha256, fetchImpl }) {
  const key = normalizeR2ObjectKey(objectKey);
  const endpoint = buildR2ObjectUrl(accountId, key);
  const headers = r2Headers(token);
  const preflight = await safeFetch(fetchImpl, endpoint, { method: "GET", headers }, "CB530_R2_PRECHECK_FAILED");
  if (preflight.status !== 404) {
    throw new CloudBackupError(preflight.status >= 200 && preflight.status < 300 ? "CB530_R2_OBJECT_EXISTS" : "CB530_R2_PRECHECK_FAILED");
  }
  const body = readBoundedFile(sourcePath, "CB530_R2_SOURCE_INVALID");
  if (sha256(body) !== expectedSha256) {
    throw new CloudBackupError("CB530_R2_SOURCE_HASH_MISMATCH");
  }
  const put = await safeFetch(fetchImpl, endpoint, {
    method: "PUT",
    headers: { ...headers, "content-type": contentTypeFor(key) },
    body,
  }, "CB530_R2_PUT_FAILED");
  if (!isSuccess(put.status)) {
    throw new CloudBackupError("CB530_R2_PUT_FAILED");
  }
  const downloaded = await getR2Object({
    accountId,
    token,
    objectKey: key,
    fetchImpl,
    expectedSha256,
  });
  return Object.freeze({
    object_key: key,
    sha256: expectedSha256,
    bytes: body.length,
    put_status: put.status,
    get_status: downloaded.status,
    etag_present: Boolean(put.headers?.get?.("etag") || downloaded.etag_present),
    body: downloaded.body,
  });
}

async function getR2Object({ accountId, token, objectKey, fetchImpl, expectedSha256 }) {
  const key = normalizeR2ObjectKey(objectKey);
  const response = await safeFetch(fetchImpl, buildR2ObjectUrl(accountId, key), {
    method: "GET",
    headers: r2Headers(token),
  }, "CB530_R2_GET_FAILED");
  if (!isSuccess(response.status)) {
    throw new CloudBackupError("CB530_R2_GET_FAILED");
  }
  const body = await responseBuffer(response, "CB530_R2_GET_FAILED");
  if (expectedSha256 !== null && sha256(body) !== expectedSha256) {
    throw new CloudBackupError("CB530_R2_READBACK_HASH_MISMATCH");
  }
  return Object.freeze({
    status: response.status,
    body,
    etag_present: Boolean(response.headers?.get?.("etag")),
  });
}

async function putOciObject({ parUrl, objectKey, sourcePath, expectedSha256, fetchImpl }) {
  const key = normalizeOciObjectKey(objectKey);
  const body = readBoundedFile(sourcePath, "CB530_OCI_SOURCE_INVALID");
  if (sha256(body) !== expectedSha256) {
    throw new CloudBackupError("CB530_OCI_SOURCE_HASH_MISMATCH");
  }
  const response = await safeFetch(fetchImpl, buildOciObjectUrl(parUrl, key), {
    method: "PUT",
    headers: { "content-type": contentTypeFor(key), "if-none-match": "*" },
    body,
  }, "CB530_OCI_PUT_FAILED");
  if (!isSuccess(response.status)) {
    throw new CloudBackupError("CB530_OCI_PUT_FAILED");
  }
  return Object.freeze({
    object_key: key,
    sha256: expectedSha256,
    bytes: body.length,
    put_status: response.status,
    etag_present: Boolean(response.headers?.get?.("etag")),
  });
}

async function readOciObjectIfAllowed({ parUrl, objectKey, expectedSha256, fetchImpl }) {
  const response = await safeFetch(fetchImpl, buildOciObjectUrl(parUrl, normalizeOciObjectKey(objectKey)), {
    method: "GET",
  }, "CB530_OCI_READBACK_FAILED");
  if (isSuccess(response.status)) {
    const body = await responseBuffer(response, "CB530_OCI_READBACK_FAILED");
    if (sha256(body) !== expectedSha256) {
      throw new CloudBackupError("CB530_OCI_READBACK_HASH_MISMATCH");
    }
    return Object.freeze({ verified: true, state: "verified" });
  }
  if ([401, 403, 404, 405].includes(response.status)) {
    return Object.freeze({ verified: false, state: "activation_pending_write_only_par" });
  }
  throw new CloudBackupError("CB530_OCI_READBACK_FAILED");
}

function restoreDownloadedR2Bundle({ backup, downloaded, restoreRoot }) {
  const root = ensureDirectory(restoreRoot);
  const temporaryRoot = fs.mkdtempSync(path.join(root, ".cb530-r2-readback-"));
  try {
    const bundle = path.join(temporaryRoot, backup.manifest.backup_id);
    fs.mkdirSync(bundle, { mode: 0o700 });
    for (const filename of SNAPSHOT_FILENAMES) {
      const body = downloaded[filename];
      if (!Buffer.isBuffer(body)) {
        throw new CloudBackupError("CB530_R2_READBACK_INCOMPLETE");
      }
      writeBufferDurable(path.join(bundle, filename), body);
    }
    const restored = restoreBackupIsolated({
      bundlePath: bundle,
      restoreRoot: root,
      networkDisabled: true,
    });
    return Object.freeze({
      ...restored,
      r2_readback_verified: true,
      r2_provider_operations: 0,
      promoted: false,
    });
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

function buildR2ObjectUrl(accountId, objectKey) {
  const account = String(accountId || "").trim();
  if (!/^[a-f0-9]{32}$/i.test(account)) {
    throw new CloudBackupError("CB530_R2_ACCOUNT_INVALID");
  }
  const key = normalizeR2ObjectKey(objectKey);
  return `${R2_API_ROOT}/accounts/${account}/r2/buckets/${R2_BUCKET}/objects/${encodeObjectKey(key)}`;
}

function buildOciObjectUrl(parUrl, objectKey) {
  const key = normalizeOciObjectKey(objectKey);
  let parsed;
  try {
    parsed = new URL(String(parUrl || "").trim());
  } catch {
    throw new CloudBackupError("CB530_OCI_PAR_INVALID");
  }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || !parsed.pathname.endsWith("/o/")) {
    throw new CloudBackupError("CB530_OCI_PAR_INVALID");
  }
  parsed.pathname = `${parsed.pathname}${encodeObjectKey(key)}`;
  return parsed.toString();
}

function r2ObjectKey(backupId, filename) {
  const id = normalizeBackupId(backupId);
  if (!SNAPSHOT_FILENAMES.includes(filename)) {
    throw new CloudBackupError("CB530_OBJECT_FILENAME_INVALID");
  }
  return `${R2_SNAPSHOT_PREFIX}${id}/${filename}`;
}

function ociObjectKey(backupId, filename) {
  const id = normalizeBackupId(backupId);
  if (!SNAPSHOT_FILENAMES.includes(filename)) {
    throw new CloudBackupError("CB530_OBJECT_FILENAME_INVALID");
  }
  return `${OCI_SNAPSHOT_PREFIX}${id}/${filename}`;
}

function normalizeR2ObjectKey(value) {
  const key = String(value || "");
  if (!new RegExp(`^${escapeRegExp(R2_SNAPSHOT_PREFIX)}backup_[a-f0-9]{24}/(?:runtime\\.sqlite3|manifest\\.json)$`).test(key)) {
    throw new CloudBackupError("CB530_R2_OBJECT_SCOPE_INVALID");
  }
  return key;
}

function normalizeOciObjectKey(value) {
  const key = String(value || "");
  if (!new RegExp(`^${escapeRegExp(OCI_SNAPSHOT_PREFIX)}backup_[a-f0-9]{24}/(?:runtime\\.sqlite3|manifest\\.json)$`).test(key)) {
    throw new CloudBackupError("CB530_OCI_OBJECT_SCOPE_INVALID");
  }
  return key;
}

function normalizeBackupId(value) {
  const id = String(value || "");
  if (!/^backup_[a-f0-9]{24}$/.test(id)) {
    throw new CloudBackupError("CB530_BACKUP_ID_INVALID");
  }
  return id;
}

function r2Headers(token) {
  const value = String(token || "").trim();
  if (!/^[A-Za-z0-9._~-]{20,256}$/.test(value)) {
    throw new CloudBackupError("CB530_R2_TOKEN_INVALID");
  }
  return {
    authorization: `Bearer ${value}`,
    "cf-r2-data-catalog-check": "true",
  };
}

function readCredentialFile(filePath, code) {
  const value = readTextFile(filePath, code).trim();
  if (!value || /[\r\n\0]/.test(value)) {
    throw new CloudBackupError(code);
  }
  return value;
}

function readTextFile(filePath, code) {
  try {
    return fs.readFileSync(requireAbsolutePath(filePath, code), "utf8");
  } catch (error) {
    if (error instanceof CloudBackupError) {
      throw error;
    }
    throw new CloudBackupError(code);
  }
}

function requireAbsolutePath(value, code) {
  const candidate = String(value || "");
  if (!path.isAbsolute(candidate) || candidate.includes("\0")) {
    throw new CloudBackupError(code);
  }
  return path.resolve(candidate);
}

function assertRegularFile(filePath, code) {
  try {
    const stat = fs.lstatSync(filePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error("not_regular");
    }
  } catch {
    throw new CloudBackupError(code);
  }
}

function ensureDirectory(directory) {
  const resolved = requireAbsolutePath(directory, "CB530_DIRECTORY_INVALID");
  fs.mkdirSync(resolved, { recursive: true, mode: 0o700 });
  const stat = fs.statSync(resolved);
  if (!stat.isDirectory()) {
    throw new CloudBackupError("CB530_DIRECTORY_INVALID");
  }
  return resolved;
}

function readBoundedFile(filePath, code) {
  assertRegularFile(filePath, code);
  try {
    const size = fs.statSync(filePath).size;
    if (size < 1 || size > MAX_OBJECT_BYTES) {
      throw new Error("size");
    }
    return fs.readFileSync(filePath);
  } catch {
    throw new CloudBackupError(code);
  }
}

function writeBufferDurable(targetPath, data) {
  const target = requireAbsolutePath(targetPath, "CB530_WRITE_PATH_INVALID");
  const parent = ensureDirectory(path.dirname(target));
  const temporary = path.join(parent, `.${path.basename(target)}.${crypto.randomUUID()}.tmp`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, data);
    fs.fsyncSync(descriptor);
  } catch {
    throw new CloudBackupError("CB530_WRITE_FAILED");
  } finally {
    if (descriptor !== undefined) {
      fs.closeSync(descriptor);
    }
  }
  try {
    fs.renameSync(temporary, target);
    fs.chmodSync(target, 0o600);
    fsyncDirectory(parent);
  } catch {
    try {
      fs.rmSync(temporary, { force: true });
    } catch {
      // The target write already failed; the caller receives a stable code.
    }
    throw new CloudBackupError("CB530_WRITE_FAILED");
  }
}

function writeJsonDurable(targetPath, value) {
  const serialized = JSON.stringify(value, null, 2).concat("\n");
  if (/-----BEGIN|\bBearer\s+[A-Za-z0-9._~-]{12,}/i.test(serialized) || serialized.includes("/var/") || serialized.includes("/home/")) {
    throw new CloudBackupError("CB530_RECEIPT_PRIVACY_VIOLATION");
  }
  writeBufferDurable(targetPath, Buffer.from(serialized, "utf8"));
}

function fsyncDirectory(directory) {
  let descriptor;
  try {
    descriptor = fs.openSync(directory, "r");
    fs.fsyncSync(descriptor);
  } finally {
    if (descriptor !== undefined) {
      fs.closeSync(descriptor);
    }
  }
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function sha256File(filePath) {
  assertRegularFile(filePath, "CB530_HASH_SOURCE_INVALID");
  const hash = crypto.createHash("sha256");
  const descriptor = fs.openSync(filePath, "r");
  try {
    const buffer = Buffer.allocUnsafe(1024 * 1024);
    let offset = 0;
    while (true) {
      const bytes = fs.readSync(descriptor, buffer, 0, buffer.length, offset);
      if (bytes === 0) {
        break;
      }
      hash.update(buffer.subarray(0, bytes));
      offset += bytes;
    }
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest("hex");
}

function contentTypeFor(key) {
  return key.endsWith("manifest.json") ? "application/json" : "application/vnd.sqlite3";
}

function encodeObjectKey(key) {
  return key.split("/").map((segment) => encodeURIComponent(segment)).join("/");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isSuccess(status) {
  return Number.isInteger(status) && status >= 200 && status < 300;
}

function assertFetch(fetchImpl) {
  if (typeof fetchImpl !== "function") {
    throw new CloudBackupError("CB530_FETCH_UNAVAILABLE");
  }
}

async function safeFetch(fetchImpl, url, options, code) {
  try {
    return await fetchImpl(url, options);
  } catch {
    throw new CloudBackupError(code);
  }
}

async function responseBuffer(response, code) {
  try {
    return Buffer.from(await response.arrayBuffer());
  } catch {
    throw new CloudBackupError(code);
  }
}

function withoutBody(value) {
  const { body, ...rest } = value;
  return Object.freeze(rest);
}

function withoutDownloaded(value) {
  const { downloaded, ...rest } = value;
  return Object.freeze(rest);
}

module.exports = {
  CloudBackupError,
  buildOciObjectUrl,
  buildR2ObjectUrl,
  bootstrapRuntimeDatabase,
  ociObjectKey,
  r2ObjectKey,
  readCredentialFile,
  restoreRemoteBackup,
  runCloudBackup,
};
