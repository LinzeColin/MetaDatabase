const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const PRODUCT_VERSION = "v0.0.0.5";
const BACKUP_SCHEMA = "cyberboss.backup-manifest.v3";
const R2_BUCKET = "cyberboss-cold";
const R2_PREFIX = "ovh-singapore-vps-1/";
const OCI_PREFIX = "cyberboss-cold-backup/ovh-singapore-vps-1/";
const OCI_BUCKET_REFERENCE = "oci-bucket-name";
const EXCLUDED_CONTENT = Object.freeze([
  "codex_auth",
  "wechat_cookie",
  "wechat_token",
  "credentials",
  "workspace_cache",
  "build_artifacts",
]);
const SENSITIVE_BACKUP_PATTERN = /-----BEGIN|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bwxid_[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~-]{12,}/i;

class CanonicalBackupError extends Error {
  constructor(code) {
    super(code);
    this.name = "CanonicalBackupError";
    this.code = code;
  }
}

function createOnlineBackup({
  sourceDbPath,
  outputDir,
  sourceCommit,
  createdAt,
  scopePolicy,
  configReferences = [],
  beforeSerialize = null,
  afterSerialize = null,
  crashPoint = "",
} = {}) {
  const source = resolveExistingDatabase(sourceDbPath);
  const output = resolveDirectory(outputDir);
  const commit = normalizeCommit(sourceCommit);
  const created = normalizeTimestamp(createdAt);
  const scope = validateBackupScope(scopePolicy);
  const references = normalizeConfigReferences(configReferences);
  if (!commit || !created) {
    throw new CanonicalBackupError("BACKUP_REQUIRED_FACT_INVALID");
  }
  if (beforeSerialize !== null && typeof beforeSerialize !== "function") {
    throw new CanonicalBackupError("BACKUP_HOOK_INVALID");
  }
  if (afterSerialize !== null && typeof afterSerialize !== "function") {
    throw new CanonicalBackupError("BACKUP_HOOK_INVALID");
  }
  if (!["", "before_publish", "after_publish_before_dirsync"].includes(crashPoint)) {
    throw new CanonicalBackupError("BACKUP_CRASH_POINT_INVALID");
  }

  let sourceDatabase;
  let image;
  try {
    sourceDatabase = new DatabaseSync(source, { readOnly: true });
    if (beforeSerialize) {
      beforeSerialize();
    }
    image = Buffer.from(sourceDatabase.serialize());
    if (afterSerialize) {
      afterSerialize();
    }
  } catch (error) {
    if (error instanceof CanonicalBackupError) {
      throw error;
    }
    throw new CanonicalBackupError("BACKUP_SNAPSHOT_FAILED");
  } finally {
    if (sourceDatabase) {
      sourceDatabase.close();
    }
  }
  if (!image || image.length === 0) {
    throw new CanonicalBackupError("BACKUP_SNAPSHOT_EMPTY");
  }
  assertSnapshotPrivacy(image);
  const snapshotSha256 = sha256(image);
  const backupId = `backup_${sha256(`${commit}|${created}|${snapshotSha256}`).slice(0, 24)}`;
  const bundlePath = path.join(output, backupId);
  if (fs.existsSync(bundlePath)) {
    const existing = readBackupBundle(bundlePath);
    if (
      existing.manifest.source_commit !== commit ||
      existing.manifest.created_at !== created ||
      existing.manifest.archive.sha256 !== snapshotSha256
    ) {
      throw new CanonicalBackupError("BACKUP_ID_COLLISION");
    }
    return Object.freeze({ ...existing, reused: true });
  }

  const staging = path.join(output, `.${backupId}.${crypto.randomUUID()}.staging`);
  let published = false;
  try {
    fs.mkdirSync(staging, { recursive: false, mode: 0o700 });
    const snapshotPath = path.join(staging, "runtime.sqlite3");
    writeFileDurable(snapshotPath, image, 0o600);
    const database = describeDatabase(snapshotPath);
    const manifest = buildManifest({
      backupId,
      createdAt: created,
      sourceCommit: commit,
      snapshotSha256,
      snapshotBytes: image.length,
      database,
      configReferences: references,
      scope,
    });
    writeFileDurable(path.join(staging, "manifest.json"), Buffer.from(`${stableJson(manifest)}\n`, "utf8"), 0o600);
    fsyncDirectory(staging);
    if (crashPoint === "before_publish") {
      throw new CanonicalBackupError("BACKUP_CRASH_BEFORE_PUBLISH");
    }
    fs.renameSync(staging, bundlePath);
    published = true;
    if (crashPoint === "after_publish_before_dirsync") {
      throw new CanonicalBackupError("BACKUP_CRASH_AFTER_PUBLISH");
    }
    fsyncDirectory(output);
    return Object.freeze({ ...readBackupBundle(bundlePath), reused: false });
  } finally {
    if (!published && fs.existsSync(staging)) {
      fs.rmSync(staging, { recursive: true, force: true });
    }
  }
}

function restoreBackupIsolated({ bundlePath, restoreRoot, networkDisabled } = {}) {
  if (networkDisabled !== true) {
    throw new CanonicalBackupError("RESTORE_NETWORK_MUST_BE_DISABLED");
  }
  const bundle = readBackupBundle(bundlePath);
  const root = resolveDirectory(restoreRoot || os.tmpdir());
  const isolated = fs.mkdtempSync(path.join(root, ".cyberboss-restore-"));
  try {
    const restored = path.join(isolated, "runtime.sqlite3");
    copyFileDurable(bundle.snapshotPath, restored);
    const description = describeDatabase(restored);
    if (
      description.sqlite_integrity !== "ok" ||
      description.logical_digest !== bundle.manifest.sqlite.logical_digest ||
      stableJson(description.table_counts) !== stableJson(bundle.manifest.sqlite.table_counts) ||
      stableJson(description.table_digests) !== stableJson(bundle.manifest.sqlite.table_digests)
    ) {
      throw new CanonicalBackupError("RESTORE_LOGICAL_DIGEST_MISMATCH");
    }
    return Object.freeze({
      status: "passed",
      backup_id: bundle.manifest.backup_id,
      archive_sha256: bundle.manifest.archive.sha256,
      sqlite_integrity: description.sqlite_integrity,
      logical_digest: description.logical_digest,
      table_counts: cloneJson(description.table_counts),
      network_disabled: true,
      promoted: false,
      real_provider_operations: 0,
    });
  } finally {
    fs.rmSync(isolated, { recursive: true, force: true });
  }
}

function simulateRemoteUpload({ bundlePath, provider, simulatorRoot, scopePolicy } = {}) {
  const bundle = readBackupBundle(bundlePath);
  const scope = validateBackupScope(scopePolicy);
  const root = resolveDirectory(simulatorRoot);
  if (!["r2", "oci"].includes(provider)) {
    throw new CanonicalBackupError("BACKUP_PROVIDER_INVALID");
  }
  const remote = provider === "r2"
    ? { bucket: scope.r2.bucket, prefix: `${scope.r2.prefix}snapshots/`, bucket_reference: null }
    : { bucket: null, prefix: `${scope.oci.prefix}snapshots/`, bucket_reference: scope.oci.bucket_reference };
  const baseKey = `${remote.prefix}${bundle.manifest.backup_id}`;
  const snapshotKey = `${baseKey}/runtime.sqlite3`;
  const manifestKey = `${baseKey}/manifest.json`;
  const namespace = provider === "r2" ? path.join(provider, remote.bucket) : provider;
  const snapshotTarget = resolveWithin(root, path.join(namespace, snapshotKey));
  const manifestTarget = resolveWithin(root, path.join(namespace, manifestKey));
  writeImmutableObject(snapshotTarget, bundle.snapshotPath, bundle.manifest.archive.sha256);
  writeImmutableObject(manifestTarget, bundle.manifestPath, sha256File(bundle.manifestPath));
  if (sha256File(snapshotTarget) !== bundle.manifest.archive.sha256 || sha256File(manifestTarget) !== sha256File(bundle.manifestPath)) {
    throw new CanonicalBackupError("BACKUP_SIMULATOR_HASH_MISMATCH");
  }
  return Object.freeze({
    provider,
    state: "simulator_verified",
    bucket: remote.bucket,
    bucket_reference: remote.bucket_reference,
    object_key: snapshotKey,
    manifest_key: manifestKey,
    archive_sha256: bundle.manifest.archive.sha256,
    manifest_sha256: sha256File(bundle.manifestPath),
    metadata_verified: true,
    real_remote_receipt: false,
    real_provider_operations: 0,
  });
}

function readBackupBundle(bundlePath) {
  const bundle = resolveExistingDirectory(bundlePath, "BACKUP_BUNDLE_UNAVAILABLE");
  const manifestPath = path.join(bundle, "manifest.json");
  const snapshotPath = path.join(bundle, "runtime.sqlite3");
  if (!fs.existsSync(manifestPath) || !fs.existsSync(snapshotPath)) {
    throw new CanonicalBackupError("BACKUP_BUNDLE_INCOMPLETE");
  }
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch {
    throw new CanonicalBackupError("BACKUP_MANIFEST_INVALID");
  }
  assertManifest(manifest);
  if (path.basename(bundle) !== manifest.backup_id) {
    throw new CanonicalBackupError("BACKUP_BUNDLE_ID_MISMATCH");
  }
  if (sha256File(snapshotPath) !== manifest.archive.sha256 || fs.statSync(snapshotPath).size !== manifest.archive.bytes) {
    throw new CanonicalBackupError("BACKUP_ARCHIVE_HASH_MISMATCH");
  }
  assertSnapshotPrivacy(fs.readFileSync(snapshotPath));
  const description = describeDatabase(snapshotPath);
  if (
    description.sqlite_integrity !== manifest.sqlite.sqlite_integrity ||
    description.schema_version !== manifest.sqlite.schema_version ||
    description.logical_digest !== manifest.sqlite.logical_digest ||
    stableJson(description.table_counts) !== stableJson(manifest.sqlite.table_counts) ||
    stableJson(description.table_digests) !== stableJson(manifest.sqlite.table_digests)
  ) {
    throw new CanonicalBackupError("BACKUP_LOGICAL_DIGEST_MISMATCH");
  }
  return Object.freeze({
    bundlePath: bundle,
    manifestPath,
    snapshotPath,
    manifest: cloneJson(manifest),
  });
}

function validateBackupScope(policy) {
  assertPlainObject(policy, "BACKUP_SCOPE_POLICY_INVALID");
  const cloudflare = policy.cloudflare;
  const oci = policy.oci;
  assertPlainObject(cloudflare, "BACKUP_SCOPE_POLICY_INVALID");
  assertPlainObject(cloudflare.r2, "BACKUP_SCOPE_POLICY_INVALID");
  assertPlainObject(oci, "BACKUP_SCOPE_POLICY_INVALID");
  if (
    policy.schema_version !== 1 ||
    cloudflare.r2.bucket !== R2_BUCKET ||
    cloudflare.r2.object_prefix !== R2_PREFIX ||
    cloudflare.r2.public_access !== false ||
    oci.object_prefix !== OCI_PREFIX ||
    oci.bucket_slot !== OCI_BUCKET_REFERENCE ||
    oci.public_access !== false
  ) {
    throw new CanonicalBackupError("BACKUP_SCOPE_POLICY_INVALID");
  }
  return Object.freeze({
    r2: Object.freeze({ bucket: R2_BUCKET, prefix: R2_PREFIX }),
    oci: Object.freeze({ bucket_reference: OCI_BUCKET_REFERENCE, prefix: OCI_PREFIX }),
  });
}

function buildManifest({
  backupId,
  createdAt,
  sourceCommit,
  snapshotSha256,
  snapshotBytes,
  database,
  configReferences,
  scope,
}) {
  const manifest = {
    schema_version: BACKUP_SCHEMA,
    product_version: PRODUCT_VERSION,
    backup_id: backupId,
    created_at: createdAt,
    source_commit: sourceCommit,
    archive: {
      filename: "runtime.sqlite3",
      sha256: snapshotSha256,
      bytes: snapshotBytes,
    },
    sqlite: database,
    config_references: configReferences,
    excluded: [...EXCLUDED_CONTENT],
    remote: {
      r2: {
        state: "activation_pending",
        bucket: scope.r2.bucket,
        prefix: `${scope.r2.prefix}snapshots/`,
        real_remote_receipt: false,
      },
      oci: {
        state: "activation_pending",
        bucket_reference: scope.oci.bucket_reference,
        prefix: `${scope.oci.prefix}snapshots/`,
        real_remote_receipt: false,
      },
    },
    counters: {
      real_r2_operations: 0,
      real_oci_operations: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    },
  };
  assertManifest(manifest);
  return Object.freeze(cloneJson(manifest));
}

function assertManifest(manifest) {
  assertPlainObject(manifest, "BACKUP_MANIFEST_INVALID");
  assertExactKeys(manifest, new Set([
    "schema_version", "product_version", "backup_id", "created_at", "source_commit",
    "archive", "sqlite", "config_references", "excluded", "remote", "counters",
  ]), "BACKUP_MANIFEST_INVALID");
  if (
    manifest.schema_version !== BACKUP_SCHEMA ||
    manifest.product_version !== PRODUCT_VERSION ||
    !/^backup_[a-f0-9]{24}$/.test(manifest.backup_id) ||
    !normalizeTimestamp(manifest.created_at) ||
    !normalizeCommit(manifest.source_commit)
  ) {
    throw new CanonicalBackupError("BACKUP_MANIFEST_INVALID");
  }
  assertPlainObject(manifest.archive, "BACKUP_MANIFEST_INVALID");
  assertPlainObject(manifest.sqlite, "BACKUP_MANIFEST_INVALID");
  assertPlainObject(manifest.remote, "BACKUP_MANIFEST_INVALID");
  assertPlainObject(manifest.remote.r2, "BACKUP_MANIFEST_INVALID");
  assertPlainObject(manifest.remote.oci, "BACKUP_MANIFEST_INVALID");
  assertPlainObject(manifest.counters, "BACKUP_MANIFEST_INVALID");
  if (
    manifest.archive.filename !== "runtime.sqlite3" ||
    !/^[a-f0-9]{64}$/.test(manifest.archive.sha256) ||
    !Number.isSafeInteger(manifest.archive.bytes) || manifest.archive.bytes < 1 ||
    manifest.sqlite.sqlite_integrity !== "ok" ||
    !Number.isSafeInteger(manifest.sqlite.schema_version) || manifest.sqlite.schema_version < 0 ||
    !/^[a-f0-9]{64}$/.test(manifest.sqlite.logical_digest) ||
    !isPlainObject(manifest.sqlite.table_counts) ||
    !isPlainObject(manifest.sqlite.table_digests) ||
    manifest.remote.r2.state !== "activation_pending" ||
    manifest.remote.r2.bucket !== R2_BUCKET ||
    manifest.remote.r2.prefix !== `${R2_PREFIX}snapshots/` ||
    manifest.remote.r2.real_remote_receipt !== false ||
    manifest.remote.oci.state !== "activation_pending" ||
    manifest.remote.oci.bucket_reference !== OCI_BUCKET_REFERENCE ||
    manifest.remote.oci.prefix !== `${OCI_PREFIX}snapshots/` ||
    manifest.remote.oci.real_remote_receipt !== false ||
    manifest.counters.real_r2_operations !== 0 ||
    manifest.counters.real_oci_operations !== 0 ||
    manifest.counters.control_plane_llm_calls !== 0 ||
    manifest.counters.operations_llm_calls !== 0 ||
    manifest.counters.macos_launchd_dependency !== false ||
    !sameStrings(manifest.excluded, EXCLUDED_CONTENT)
  ) {
    throw new CanonicalBackupError("BACKUP_MANIFEST_INVALID");
  }
  const tableNames = Object.keys(manifest.sqlite.table_counts).sort();
  if (!sameStrings(tableNames, Object.keys(manifest.sqlite.table_digests).sort())) {
    throw new CanonicalBackupError("BACKUP_MANIFEST_INVALID");
  }
  for (const table of tableNames) {
    if (!/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(table) || !Number.isSafeInteger(manifest.sqlite.table_counts[table]) || manifest.sqlite.table_counts[table] < 0 || !/^[a-f0-9]{64}$/.test(manifest.sqlite.table_digests[table])) {
      throw new CanonicalBackupError("BACKUP_MANIFEST_INVALID");
    }
  }
  normalizeConfigReferences(manifest.config_references);
  const serialized = stableJson(manifest);
  if (SENSITIVE_BACKUP_PATTERN.test(serialized) || serialized.includes("/var/") || serialized.includes("/home/")) {
    throw new CanonicalBackupError("BACKUP_PRIVACY_VIOLATION");
  }
}

function describeDatabase(snapshotPath) {
  let database;
  try {
    database = new DatabaseSync(snapshotPath, { readOnly: true });
    const integrity = String(database.prepare("PRAGMA integrity_check").get().integrity_check || "");
    if (integrity !== "ok") {
      throw new CanonicalBackupError("BACKUP_SQLITE_INTEGRITY_FAILED");
    }
    const tables = database.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all()
      .map((row) => String(row.name));
    const tableCounts = {};
    const tableDigests = {};
    for (const table of tables) {
      const quoted = quoteIdentifier(table);
      const columns = database.prepare(`PRAGMA table_info(${quoted})`).all().map((column) => String(column.name));
      if (columns.length === 0) {
        throw new CanonicalBackupError("BACKUP_TABLE_SCHEMA_INVALID");
      }
      const selection = columns.map(quoteIdentifier).join(", ");
      const ordering = columns.map((column) => `${quoteIdentifier(column)} COLLATE BINARY`).join(", ");
      const rows = database.prepare(`SELECT ${selection} FROM ${quoted} ORDER BY ${ordering}`).all();
      tableCounts[table] = rows.length;
      const digest = crypto.createHash("sha256");
      digest.update(stableJson({ table, columns }));
      for (const row of rows) {
        digest.update(stableJson(normalizeSqlValue(row)));
      }
      tableDigests[table] = digest.digest("hex");
    }
    const schemaVersion = tables.includes("schema_migrations")
      ? Number(database.prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").get().version)
      : 0;
    if (!Number.isSafeInteger(schemaVersion) || schemaVersion < 0) {
      throw new CanonicalBackupError("BACKUP_SCHEMA_VERSION_INVALID");
    }
    const logicalDigest = sha256(stableJson({ schema_version: schemaVersion, table_counts: tableCounts, table_digests: tableDigests }));
    return Object.freeze({
      sqlite_integrity: "ok",
      schema_version: schemaVersion,
      table_counts: tableCounts,
      table_digests: tableDigests,
      logical_digest: logicalDigest,
    });
  } catch (error) {
    if (error instanceof CanonicalBackupError) {
      throw error;
    }
    throw new CanonicalBackupError("BACKUP_SQLITE_DESCRIBE_FAILED");
  } finally {
    if (database) {
      database.close();
    }
  }
}

function normalizeSqlValue(value) {
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    return { blob_sha256: sha256(Buffer.from(value)), bytes: value.length };
  }
  if (Array.isArray(value)) {
    return value.map(normalizeSqlValue);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalizeSqlValue(value[key])]));
  }
  if (value === null || typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) {
    return value;
  }
  throw new CanonicalBackupError("BACKUP_SQLITE_VALUE_INVALID");
}

function assertSnapshotPrivacy(image) {
  const text = Buffer.from(image).toString("utf8");
  if (SENSITIVE_BACKUP_PATTERN.test(text)) {
    throw new CanonicalBackupError("BACKUP_PRIVACY_VIOLATION");
  }
}

function writeImmutableObject(targetPath, sourcePath, expectedSha256) {
  if (fs.existsSync(targetPath)) {
    if (sha256File(targetPath) !== expectedSha256) {
      throw new CanonicalBackupError("BACKUP_OBJECT_COLLISION");
    }
    return;
  }
  fs.mkdirSync(path.dirname(targetPath), { recursive: true, mode: 0o700 });
  copyFileDurable(sourcePath, targetPath);
  if (sha256File(targetPath) !== expectedSha256) {
    throw new CanonicalBackupError("BACKUP_OBJECT_HASH_MISMATCH");
  }
}

function copyFileDurable(sourcePath, targetPath) {
  const temporary = `${targetPath}.${crypto.randomUUID()}.tmp`;
  let renamed = false;
  try {
    fs.copyFileSync(sourcePath, temporary, fs.constants.COPYFILE_EXCL);
    const descriptor = fs.openSync(temporary, "r");
    try {
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    fs.renameSync(temporary, targetPath);
    renamed = true;
    fsyncDirectory(path.dirname(targetPath));
  } finally {
    if (!renamed && fs.existsSync(temporary)) {
      fs.rmSync(temporary, { force: true });
    }
  }
}

function writeFileDurable(targetPath, payload, mode) {
  const descriptor = fs.openSync(targetPath, "wx", mode);
  try {
    fs.writeFileSync(descriptor, payload);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

function fsyncDirectory(directoryPath) {
  const descriptor = fs.openSync(directoryPath, "r");
  try {
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

function resolveExistingDatabase(value) {
  const candidate = resolveExistingFile(value, "BACKUP_SOURCE_UNAVAILABLE");
  if (path.extname(candidate) !== ".db" && path.extname(candidate) !== ".sqlite" && path.extname(candidate) !== ".sqlite3") {
    throw new CanonicalBackupError("BACKUP_SOURCE_EXTENSION_INVALID");
  }
  return candidate;
}

function resolveExistingFile(value, code) {
  const text = normalizeText(value);
  const candidate = text ? path.resolve(text) : "";
  if (!candidate || !fs.existsSync(candidate) || !fs.statSync(candidate).isFile() || fs.lstatSync(candidate).isSymbolicLink()) {
    throw new CanonicalBackupError(code);
  }
  return candidate;
}

function resolveExistingDirectory(value, code) {
  const text = normalizeText(value);
  const candidate = text ? path.resolve(text) : "";
  if (!candidate || !fs.existsSync(candidate) || !fs.statSync(candidate).isDirectory() || fs.lstatSync(candidate).isSymbolicLink()) {
    throw new CanonicalBackupError(code);
  }
  return candidate;
}

function resolveDirectory(value) {
  const text = normalizeText(value);
  if (!text) {
    throw new CanonicalBackupError("BACKUP_OUTPUT_REQUIRED");
  }
  const directory = path.resolve(text);
  if (fs.existsSync(directory) && (!fs.statSync(directory).isDirectory() || fs.lstatSync(directory).isSymbolicLink())) {
    throw new CanonicalBackupError("BACKUP_OUTPUT_INVALID");
  }
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  return directory;
}

function resolveWithin(root, relative) {
  const rootPath = path.resolve(root);
  const target = path.resolve(rootPath, relative);
  if (target !== rootPath && !target.startsWith(`${rootPath}${path.sep}`)) {
    throw new CanonicalBackupError("BACKUP_OBJECT_PATH_ESCAPE");
  }
  return target;
}

function normalizeConfigReferences(value) {
  if (!Array.isArray(value) || value.length > 16) {
    throw new CanonicalBackupError("BACKUP_CONFIG_REFERENCES_INVALID");
  }
  const normalized = value.map((reference) => {
    const text = normalizeText(reference);
    if (!/^[a-z][a-z0-9_-]{1,63}$/.test(text)) {
      throw new CanonicalBackupError("BACKUP_CONFIG_REFERENCES_INVALID");
    }
    return text;
  });
  if (new Set(normalized).size !== normalized.length) {
    throw new CanonicalBackupError("BACKUP_CONFIG_REFERENCES_INVALID");
  }
  return normalized.sort();
}

function normalizeTimestamp(value) {
  const text = normalizeText(value);
  const parsed = new Date(text);
  return text && Number.isFinite(parsed.getTime()) && parsed.toISOString() === text ? text : "";
}

function normalizeCommit(value) {
  const text = normalizeText(value);
  return /^[a-f0-9]{40}$/.test(text) ? text : "";
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function quoteIdentifier(value) {
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(value)) {
    throw new CanonicalBackupError("BACKUP_IDENTIFIER_INVALID");
  }
  return `"${value}"`;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertPlainObject(value, code) {
  if (!isPlainObject(value)) {
    throw new CanonicalBackupError(code);
  }
}

function assertExactKeys(value, expected, code) {
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new CanonicalBackupError(code);
  }
}

function sameStrings(value, expected) {
  return Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index]);
}

function stableJson(value) {
  return JSON.stringify(sortJson(value));
}

function sortJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortJson);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function sha256File(filePath) {
  const digest = crypto.createHash("sha256");
  const descriptor = fs.openSync(filePath, "r");
  try {
    const buffer = Buffer.allocUnsafe(1024 * 1024);
    let position = 0;
    while (true) {
      const read = fs.readSync(descriptor, buffer, 0, buffer.length, position);
      if (read === 0) {
        break;
      }
      digest.update(buffer.subarray(0, read));
      position += read;
    }
  } finally {
    fs.closeSync(descriptor);
  }
  return digest.digest("hex");
}

module.exports = {
  BACKUP_SCHEMA,
  EXCLUDED_CONTENT,
  OCI_BUCKET_REFERENCE,
  OCI_PREFIX,
  PRODUCT_VERSION,
  R2_BUCKET,
  R2_PREFIX,
  CanonicalBackupError,
  createOnlineBackup,
  readBackupBundle,
  restoreBackupIsolated,
  simulateRemoteUpload,
  validateBackupScope,
};
