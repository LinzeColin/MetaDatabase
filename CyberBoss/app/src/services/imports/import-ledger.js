"use strict";

// CB-710 / AC-023: the durable import ledger over the `imports` table.
//
// An import's identity is HMAC-free but fully determined by (user, source,
// content hash), so re-uploading the same export resolves to the same row and
// commits no duplicate facts. Progress is checkpointed, so an interrupted
// import resumes from where it stopped rather than starting over.

const { createHash } = require("node:crypto");

const SOURCES = Object.freeze(["chatgpt", "gemini", "deepseek", "claude"]);
const STATES = Object.freeze([
  "preflight",
  "running",
  "completed",
  "failed",
  "cancelled",
]);
const SHA256 = /^[a-f0-9]{64}$/;

class ImportLedgerError extends Error {
  constructor(code) {
    super(code);
    this.name = "ImportLedgerError";
    this.code = code;
  }
}

function importIdentity({ userId, source, sourceHash }) {
  if (!userId || !SOURCES.includes(source) || !SHA256.test(sourceHash || "")) {
    throw new ImportLedgerError("IMPORT_IDENTITY_INVALID");
  }
  const digest = createHash("sha256")
    .update(`${userId}\u0000${source}\u0000${sourceHash}`)
    .digest("base64url");
  return `imp_${digest.slice(0, 26)}`;
}

class SqliteImportLedger {
  constructor({ database, now = () => new Date() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new ImportLedgerError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.now = now;
  }

  #timestamp() {
    const value = this.now();
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) {
      throw new ImportLedgerError("CLOCK_INVALID");
    }
    return date.toISOString();
  }

  #rollbackQuietly() {
    try {
      this.database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; the original error is preserved.
    }
  }

  get(importId) {
    const row = this.database
      .prepare(
        `SELECT import_id, user_id, source, source_hash, object_ref, state,
                compatibility, checkpoint_json, imported_records,
                created_at, updated_at
         FROM imports WHERE import_id=?`,
      )
      .get(importId);
    return row ? Object.freeze({ ...row }) : null;
  }

  // Returns duplicate:true for a repeat upload instead of creating a second
  // import, so the same file can never be committed twice.
  begin({ userId, source, sourceHash, objectRef, compatibility = "stable" }) {
    const importId = importIdentity({ userId, source, sourceHash });
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const existing = this.database
        .prepare("SELECT import_id, state FROM imports WHERE import_id=?")
        .get(importId);
      if (existing) {
        this.database.exec("COMMIT");
        return Object.freeze({
          ...this.get(importId),
          duplicate: true,
        });
      }
      this.database
        .prepare(
          `INSERT INTO imports(
             import_id, user_id, source, source_hash, object_ref, state,
             compatibility, checkpoint_json, imported_records,
             created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, 'preflight', ?, NULL, 0, ?, ?)`,
        )
        .run(importId, userId, source, sourceHash, objectRef, compatibility, now, now);
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return Object.freeze({ ...this.get(importId), duplicate: false });
  }

  // A checkpoint only ever moves forward: a stale worker cannot rewind
  // progress another worker already recorded.
  checkpoint({ importId, checkpoint, importedRecords }) {
    if (!Number.isSafeInteger(importedRecords) || importedRecords < 0) {
      throw new ImportLedgerError("IMPORTED_RECORDS_INVALID");
    }
    const result = this.database
      .prepare(
        `UPDATE imports
         SET state='running', checkpoint_json=?, imported_records=?, updated_at=?
         WHERE import_id=? AND state IN ('preflight','running')
           AND imported_records <= ?`,
      )
      .run(
        JSON.stringify(checkpoint),
        importedRecords,
        this.#timestamp(),
        importId,
        importedRecords,
      );
    if (Number(result.changes) !== 1) {
      throw new ImportLedgerError("IMPORT_CHECKPOINT_REJECTED");
    }
    return this.get(importId);
  }

  // Resuming reads the last checkpoint; a completed import reports nothing left.
  resume(importId) {
    const row = this.get(importId);
    if (!row) {
      throw new ImportLedgerError("IMPORT_NOT_FOUND");
    }
    if (row.state === "completed") {
      return Object.freeze({
        importId,
        resumable: false,
        reason: "already_completed",
        importedRecords: Number(row.imported_records),
      });
    }
    return Object.freeze({
      importId,
      resumable: true,
      checkpoint: row.checkpoint_json ? JSON.parse(row.checkpoint_json) : null,
      importedRecords: Number(row.imported_records),
      compatibility: row.compatibility,
    });
  }

  complete({ importId, importedRecords }) {
    const result = this.database
      .prepare(
        `UPDATE imports
         SET state='completed', imported_records=?, updated_at=?
         WHERE import_id=? AND state IN ('preflight','running')`,
      )
      .run(importedRecords, this.#timestamp(), importId);
    if (Number(result.changes) !== 1) {
      throw new ImportLedgerError("IMPORT_STATE_INVALID");
    }
    return this.get(importId);
  }

  // A failure receipt is retained: the user can see that an attempt happened
  // and why, and prior successful imports are untouched.
  fail({ importId, reasonCode }) {
    const result = this.database
      .prepare(
        `UPDATE imports
         SET state='failed', checkpoint_json=?, updated_at=?
         WHERE import_id=? AND state IN ('preflight','running')`,
      )
      .run(
        JSON.stringify({ reason_code: reasonCode }),
        this.#timestamp(),
        importId,
      );
    if (Number(result.changes) !== 1) {
      throw new ImportLedgerError("IMPORT_STATE_INVALID");
    }
    return this.get(importId);
  }

  listForUser(userId, { limit = 50 } = {}) {
    return this.database
      .prepare(
        `SELECT import_id, source, state, compatibility, imported_records,
                created_at, updated_at
         FROM imports WHERE user_id=? ORDER BY created_at DESC LIMIT ?`,
      )
      .all(userId, Math.max(1, Math.min(200, Number(limit) || 50)))
      .map((row) => Object.freeze({ ...row }));
  }
}

module.exports = {
  ImportLedgerError,
  SOURCES,
  STATES,
  SqliteImportLedger,
  importIdentity,
};
