#!/usr/bin/env node

"use strict";

const fs = require("fs");
const path = require("path");

const {
  CloudBackupError,
  bootstrapRuntimeDatabase,
  readCredentialFile,
  restoreRemoteBackup,
  runCloudBackup,
} = require("../src/services/backup/cb530-cloud-backup");
const { CanonicalBackupError } = require("../src/services/backup/canonical-backup-runtime");

const RELEASE_ROOT = path.resolve(process.env.CB_RELEASE_ROOT || path.join(__dirname, "../.."));
const RUNTIME_ROOT = "/var/lib/cyberboss";
const CREDENTIAL_ROOT = "/run/credentials";

async function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArgs(argv);
    if (options.help) {
      process.stdout.write(helpText());
      return 0;
    }
    const config = loadConfig();
    if (options.command === "backup") {
      if (!fs.existsSync(config.sourceDb) && !options.bootstrapIfMissing) {
        throw new CloudBackupError("CB530_RUNTIME_DB_MISSING");
      }
      const bootstrap = options.bootstrapIfMissing
        ? bootstrapRuntimeDatabase({ sourceDbPath: config.sourceDb, schemaPath: config.schemaPath })
        : Object.freeze({ created: false });
      const result = await runCloudBackup(backupRequest(config, releaseCommit(config.releaseRoot), new Date().toISOString()));
      process.stdout.write(`${JSON.stringify(redactResult({ ...result, runtime_db_bootstrapped: bootstrap.created }))}\n`);
      return 0;
    }
    const result = await restoreRemoteBackup({
      backupId: options.backupId,
      restoreRoot: config.restoreRoot,
      r2AccountId: config.r2AccountId,
      r2Token: config.r2Token,
    });
    process.stdout.write(`${JSON.stringify(redactResult(result))}\n`);
    return 0;
  } catch (error) {
    const code = error instanceof CloudBackupError || error instanceof CanonicalBackupError
      ? error.code
      : "CB530_BACKUP_FAILED";
    process.stderr.write(`${JSON.stringify({ status: "failed", code })}\n`);
    return 2;
  }
}

function parseArgs(argv) {
  const values = Array.isArray(argv) ? argv.map((value) => String(value || "")) : [];
  const command = values[0] === "restore" ? "restore" : "backup";
  const offset = values[0] === "backup" || values[0] === "restore" ? 1 : 0;
  const options = {
    command,
    help: values.includes("--help") || values.includes("-h"),
    bootstrapIfMissing: false,
    backupId: "",
  };
  for (let index = offset; index < values.length; index += 1) {
    const flag = values[index];
    if (flag === "--help" || flag === "-h") {
      continue;
    }
    if (flag === "--bootstrap-if-missing" && command === "backup") {
      options.bootstrapIfMissing = true;
      continue;
    }
    if (flag === "--backup-id" && command === "restore") {
      const next = values[index + 1];
      if (!next || next.startsWith("--")) {
        throw new CloudBackupError("CB530_ARGUMENT_INVALID");
      }
      options.backupId = next;
      index += 1;
      continue;
    }
    throw new CloudBackupError("CB530_ARGUMENT_INVALID");
  }
  if (!options.help && command === "restore" && !options.backupId) {
    throw new CloudBackupError("CB530_BACKUP_ID_REQUIRED");
  }
  return options;
}

function loadConfig() {
  const releaseRoot = requireManagedPath(process.env.CB_RELEASE_ROOT || RELEASE_ROOT, "/opt/cyberboss-cloud", "CB530_RELEASE_ROOT_INVALID");
  const sourceDb = requireManagedPath(process.env.CB_RUNTIME_DB || `${RUNTIME_ROOT}/runtime.db`, RUNTIME_ROOT, "CB530_RUNTIME_DB_PATH_INVALID");
  const outputDir = requireManagedPath(process.env.CB_BACKUP_LOCAL_DIR || `${RUNTIME_ROOT}/snapshots`, RUNTIME_ROOT, "CB530_OUTPUT_PATH_INVALID");
  const restoreRoot = requireManagedPath(process.env.CB_RESTORE_ROOT || `${RUNTIME_ROOT}/restore-tests`, RUNTIME_ROOT, "CB530_RESTORE_PATH_INVALID");
  const receiptDir = requireManagedPath(process.env.CB_BACKUP_RECEIPT_DIR || `${RUNTIME_ROOT}/snapshots/receipts`, RUNTIME_ROOT, "CB530_RECEIPT_PATH_INVALID");
  const credentialDir = requireManagedPath(process.env.CREDENTIALS_DIRECTORY || process.env.CB_CREDENTIAL_DIR || CREDENTIAL_ROOT, "/run", "CB530_CREDENTIAL_DIR_INVALID");
  const accountFile = requireManagedPath(process.env.CB_R2_ACCOUNT_ID_FILE || path.join(credentialDir, "r2_account_id"), "/run", "CB530_R2_ACCOUNT_FILE_INVALID");
  const tokenFile = requireManagedPath(process.env.CB_R2_TOKEN_FILE || path.join(credentialDir, "r2_api_token"), "/run", "CB530_R2_TOKEN_FILE_INVALID");
  const ociFile = requireManagedPath(process.env.CB_OCI_PAR_FILE || path.join(credentialDir, "oci_par_url"), "/run", "CB530_OCI_PAR_FILE_INVALID");
  return Object.freeze({
    releaseRoot,
    sourceDb,
    outputDir,
    restoreRoot,
    receiptDir,
    schemaPath: path.join(releaseRoot, "docs/product_design/v0.0.0.4/implementation-kit/sql/runtime-spool.sql"),
    scopePolicy: readJson(path.join(releaseRoot, "docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json"), "CB530_SCOPE_POLICY_UNAVAILABLE"),
    r2AccountId: readCredentialFile(accountFile, "CB530_R2_ACCOUNT_FILE_INVALID"),
    r2Token: readCredentialFile(tokenFile, "CB530_R2_TOKEN_FILE_INVALID"),
    ociParUrl: readCredentialFile(ociFile, "CB530_OCI_PAR_FILE_INVALID"),
  });
}

function releaseCommit(releaseRoot) {
  const manifest = readJson(path.join(releaseRoot, "release-manifest.json"), "CB530_RELEASE_MANIFEST_UNAVAILABLE");
  const commit = String(manifest.release_commit || manifest.commit || "");
  if (!/^[a-f0-9]{40}$/.test(commit)) {
    throw new CloudBackupError("CB530_RELEASE_COMMIT_INVALID");
  }
  return commit;
}

function backupRequest(config, sourceCommit, createdAt) {
  if (!config || typeof config !== "object" || typeof config.sourceDb !== "string") {
    throw new CloudBackupError("CB530_RUNTIME_DB_PATH_INVALID");
  }
  return Object.freeze({
    ...config,
    sourceDbPath: config.sourceDb,
    sourceCommit,
    createdAt,
  });
}

function readJson(filePath, code) {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("invalid");
    }
    return parsed;
  } catch {
    throw new CloudBackupError(code);
  }
}

function requireManagedPath(value, root, code) {
  const candidate = String(value || "");
  if (!path.isAbsolute(candidate) || candidate.includes("\0")) {
    throw new CloudBackupError(code);
  }
  const resolved = path.resolve(candidate);
  const boundary = path.resolve(root);
  if (resolved !== boundary && !resolved.startsWith(`${boundary}${path.sep}`)) {
    throw new CloudBackupError(code);
  }
  return resolved;
}

function redactResult(result) {
  const { receipt_path, ...safe } = result;
  const serialized = JSON.stringify(safe);
  if (/Bearer\s+|-----BEGIN|\/var\/|\/home\/|\/run\/credentials/i.test(serialized)) {
    throw new CloudBackupError("CB530_OUTPUT_PRIVACY_VIOLATION");
  }
  return safe;
}

function helpText() {
  return [
    "用法：",
    "  cb530-cloud-backup.js backup --bootstrap-if-missing",
    "  cb530-cloud-backup.js restore --backup-id backup_<24位十六进制>",
    "",
    "在固定 R2/OCI scope 内执行不可覆盖备份；恢复只做网络隔离的 SQLite 校验，不提升为运行库。",
  ].join("\n").concat("\n");
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = { backupRequest, main, parseArgs };
