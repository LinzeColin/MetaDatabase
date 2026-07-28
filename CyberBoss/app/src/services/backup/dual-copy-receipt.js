"use strict";

// CB-800 / AC-035: encrypted snapshot, dual copy, isolated restore.
//
// This layers over the existing backup runtime (canonical-backup-runtime.js
// takes the SQLite online backup; cb530-cloud-backup.js talks to R2 and OCI).
// It does not replace either. What it adds is the multi-user guarantee the
// v0.0.0.8 contract needs:
//
//   * a receipt is only issued when BOTH copies landed. A single-copy upload
//     is a failure, not a receipt with a missing field — otherwise a later
//     restore discovers the second copy never existed at exactly the moment
//     the first one is unreadable.
//   * integrity is checked before decryption, so a corrupt object cannot be
//     fed to the cipher at all.
//   * restore happens against an isolated target and the relational shape is
//     verified there before anything is promoted.

const { createHash } = require("node:crypto");

const RECEIPT_SCHEMA = "cyberboss.dual-copy-backup-receipt.v1";
const SOURCES = Object.freeze(["r2", "oci"]);
const ID_PATTERN = /^[A-Za-z0-9_.-]{8,120}$/;
const MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024;

class DualCopyBackupError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "DualCopyBackupError";
    this.code = code;
    this.detail = detail;
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function assertId(value, field) {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) {
    throw new DualCopyBackupError("BACKUP_ID_INVALID", field);
  }
  return value;
}

function assertObjectClient(client, name) {
  if (
    !client ||
    typeof client.putObject !== "function" ||
    typeof client.getObject !== "function"
  ) {
    throw new DualCopyBackupError("BACKUP_OBJECT_CLIENT_REQUIRED", name);
  }
  return client;
}

function versionOf(receipt) {
  if (!receipt || typeof receipt !== "object") {
    return null;
  }
  return receipt.versionId || receipt.etag || receipt.version || null;
}

class DualCopyBackupCoordinator {
  constructor({
    snapshotRuntimeDb,
    encryptSnapshot,
    decryptSnapshot,
    validateSnapshot,
    restoreRuntimeDbIsolated,
    verifyRelations,
    r2,
    oci,
  }) {
    const required = {
      snapshotRuntimeDb,
      encryptSnapshot,
      decryptSnapshot,
      validateSnapshot,
      restoreRuntimeDbIsolated,
      verifyRelations,
    };
    for (const [name, fn] of Object.entries(required)) {
      if (typeof fn !== "function") {
        throw new DualCopyBackupError("BACKUP_DEPENDENCY_REQUIRED", name);
      }
    }
    this.snapshotRuntimeDb = snapshotRuntimeDb;
    this.encryptSnapshot = encryptSnapshot;
    this.decryptSnapshot = decryptSnapshot;
    this.validateSnapshot = validateSnapshot;
    this.restoreRuntimeDbIsolated = restoreRuntimeDbIsolated;
    this.verifyRelations = verifyRelations;
    this.r2 = assertObjectClient(r2, "r2");
    this.oci = assertObjectClient(oci, "oci");
  }

  async create({ backupId, releaseId, createdAt }) {
    assertId(backupId, "backupId");
    assertId(releaseId, "releaseId");
    const timestamp = new Date(createdAt);
    if (!Number.isFinite(timestamp.getTime())) {
      throw new DualCopyBackupError("BACKUP_CREATED_AT_INVALID", "createdAt");
    }

    const plain = Buffer.from(await this.snapshotRuntimeDb());
    if (plain.length === 0) {
      throw new DualCopyBackupError("BACKUP_SNAPSHOT_EMPTY", "snapshot");
    }
    if (plain.length > MAX_SNAPSHOT_BYTES) {
      throw new DualCopyBackupError("BACKUP_SNAPSHOT_TOO_LARGE", "snapshot");
    }
    // The plaintext is validated before encryption: an unusable snapshot must
    // never become a receipt that looks healthy until the day it is needed.
    await this.validateSnapshot(plain);
    const plainSha256 = sha256(plain);

    const encrypted = Buffer.from(await this.encryptSnapshot(plain));
    if (encrypted.length === 0) {
      throw new DualCopyBackupError("BACKUP_CIPHERTEXT_EMPTY", "encrypt");
    }
    if (encrypted.equals(plain)) {
      throw new DualCopyBackupError("BACKUP_NOT_ENCRYPTED", "encrypt");
    }
    const digest = sha256(encrypted);
    const day = timestamp.toISOString().slice(0, 10);
    const key = `CyberBoss/backups/${day}/${backupId}.enc`;
    const metadata = Object.freeze({
      sha256: digest,
      releaseId,
      createdAt: timestamp.toISOString(),
      bytes: encrypted.length,
    });

    const copies = {};
    const failures = [];
    for (const source of SOURCES) {
      try {
        const putReceipt = await this[source].putObject({ key, body: encrypted, metadata });
        const version = versionOf(putReceipt);
        if (!version) {
          failures.push(`${source}:no_version`);
          continue;
        }
        copies[source] = version;
      } catch (error) {
        failures.push(`${source}:${error && error.code ? error.code : "put_failed"}`);
      }
    }
    if (failures.length > 0) {
      // No half receipt. The caller learns which copy failed and retries the
      // whole backup; it never gets a document that claims two copies exist.
      throw new DualCopyBackupError("BACKUP_DUAL_COPY_INCOMPLETE", failures.join(","));
    }

    return Object.freeze({
      schema: RECEIPT_SCHEMA,
      backupId,
      releaseId,
      key,
      sha256: digest,
      plainSha256,
      bytes: encrypted.length,
      createdAt: timestamp.toISOString(),
      copies: Object.freeze({ r2: copies.r2, oci: copies.oci }),
      dualCopy: true,
    });
  }

  #assertReceipt(receipt) {
    if (!receipt || typeof receipt !== "object") {
      throw new DualCopyBackupError("BACKUP_RECEIPT_REQUIRED", "receipt");
    }
    if (receipt.schema !== RECEIPT_SCHEMA) {
      throw new DualCopyBackupError("BACKUP_RECEIPT_SCHEMA_UNKNOWN", "schema");
    }
    for (const field of ["key", "sha256", "plainSha256", "bytes"]) {
      if (receipt[field] === undefined || receipt[field] === null) {
        throw new DualCopyBackupError("BACKUP_RECEIPT_INCOMPLETE", field);
      }
    }
    if (
      receipt.dualCopy !== true ||
      !receipt.copies ||
      !receipt.copies.r2 ||
      !receipt.copies.oci
    ) {
      throw new DualCopyBackupError("BACKUP_RECEIPT_NOT_DUAL_COPY", "copies");
    }
    return receipt;
  }

  // Restore into an isolated target. The live runtime is never the target of
  // this call; promotion is a separate, deliberate step for the operator.
  async restore({ receipt, source = "r2", restoreRoot }) {
    this.#assertReceipt(receipt);
    if (!SOURCES.includes(source)) {
      throw new DualCopyBackupError("BACKUP_SOURCE_INVALID", "source");
    }
    if (typeof restoreRoot !== "string" || restoreRoot.length === 0) {
      throw new DualCopyBackupError("BACKUP_RESTORE_ROOT_REQUIRED", "restoreRoot");
    }

    const encrypted = Buffer.from(await this[source].getObject({ key: receipt.key }));
    // Integrity first, decryption second.
    if (encrypted.length !== receipt.bytes || sha256(encrypted) !== receipt.sha256) {
      throw new DualCopyBackupError("BACKUP_INTEGRITY_FAILED", source);
    }

    const plain = Buffer.from(await this.decryptSnapshot(encrypted));
    if (sha256(plain) !== receipt.plainSha256) {
      throw new DualCopyBackupError("BACKUP_PLAINTEXT_MISMATCH", source);
    }
    await this.validateSnapshot(plain);

    const restored = await this.restoreRuntimeDbIsolated({ snapshot: plain, restoreRoot });
    const relations = await this.verifyRelations(restored);
    if (!relations || relations.ok !== true) {
      throw new DualCopyBackupError(
        "BACKUP_RELATION_CHECK_FAILED",
        relations && relations.reason ? String(relations.reason) : "unknown",
      );
    }

    return Object.freeze({
      ok: true,
      backupId: receipt.backupId,
      releaseId: receipt.releaseId,
      source,
      isolated: true,
      restoredSha256: sha256(plain),
      relations: Object.freeze({ ...relations }),
    });
  }

  // AC-035: the second copy is only worth having if it can carry a restore on
  // its own. This proves both copies independently, in isolation.
  async verifyBothCopies({ receipt, restoreRoot }) {
    this.#assertReceipt(receipt);
    const results = {};
    for (const source of SOURCES) {
      try {
        const outcome = await this.restore({
          receipt,
          source,
          restoreRoot: `${restoreRoot}/${source}`,
        });
        results[source] = { ok: true, restoredSha256: outcome.restoredSha256 };
      } catch (error) {
        results[source] = {
          ok: false,
          code: error && error.code ? error.code : "RESTORE_FAILED",
        };
      }
    }
    return Object.freeze({
      backupId: receipt.backupId,
      r2: Object.freeze(results.r2),
      oci: Object.freeze(results.oci),
      bothRestorable: results.r2.ok === true && results.oci.ok === true,
      // If one copy is unreadable the backup is still recoverable, but it has
      // stopped being a dual copy and must be rebuilt.
      degraded: results.r2.ok !== results.oci.ok,
    });
  }
}

module.exports = {
  DualCopyBackupCoordinator,
  DualCopyBackupError,
  MAX_SNAPSHOT_BYTES,
  RECEIPT_SCHEMA,
  SOURCES,
  sha256,
};
