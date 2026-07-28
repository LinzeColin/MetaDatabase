"use strict";

// CB-610 / AC-041: invite codes are Owner-generated, stored only as an
// HMAC-SHA256 keyed hash, at least 12 characters, bounded in uses, expirable
// and revocable. The plaintext code never reaches the database or a log.

const { createHmac, randomBytes, timingSafeEqual } = require("node:crypto");

const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const MIN_CODE_LENGTH = 12;
const MAX_CODE_LENGTH = 32;
const MAX_USES = 20;
const NORMALIZED_CODE = /^[A-Z0-9]{12,32}$/;

class InviteCodeError extends Error {
  constructor(code) {
    super(code);
    this.name = "InviteCodeError";
    this.code = code;
  }
}

function normalizeCode(value) {
  return String(value === null || value === undefined ? "" : value)
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

function requireSecret(secret) {
  if (!Buffer.isBuffer(secret) || secret.length < 32) {
    throw new InviteCodeError("INVITE_SECRET_MUST_BE_AT_LEAST_32_BYTES");
  }
  return secret;
}

function hashCode(secret, value) {
  const normalized = normalizeCode(value);
  if (!NORMALIZED_CODE.test(normalized)) {
    throw new InviteCodeError("INVITE_CODE_INVALID");
  }
  return createHmac("sha256", requireSecret(secret))
    .update("cyberboss-invite-code")
    .update(normalized)
    .digest("hex");
}

// Rejection sampling keeps every alphabet symbol equally likely; the alphabet
// itself omits I/O/0/1 so an Owner can read a code aloud without ambiguity.
function generateCode(length = MIN_CODE_LENGTH) {
  if (
    !Number.isSafeInteger(length) ||
    length < MIN_CODE_LENGTH ||
    length > MAX_CODE_LENGTH
  ) {
    throw new InviteCodeError("INVITE_CODE_LENGTH_INVALID");
  }
  const limit = 256 - (256 % CODE_ALPHABET.length);
  let code = "";
  while (code.length < length) {
    for (const byte of randomBytes(length * 2)) {
      if (byte >= limit) {
        continue;
      }
      code += CODE_ALPHABET[byte % CODE_ALPHABET.length];
      if (code.length === length) {
        break;
      }
    }
  }
  return code;
}

function formatCode(code) {
  return normalizeCode(code).replace(/(.{4})(?=.)/g, "$1-");
}

class SqliteInviteCodeStore {
  constructor({ database, secret, now = () => Date.now() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new InviteCodeError("DATABASE_REQUIRED");
    }
    this.database = database;
    this.secret = requireSecret(secret);
    this.now = now;
  }

  #millis() {
    const value = this.now();
    const millis = value instanceof Date ? value.getTime() : Number(value);
    if (!Number.isFinite(millis)) {
      throw new InviteCodeError("CLOCK_INVALID");
    }
    return Math.trunc(millis);
  }

  #rollbackQuietly() {
    try {
      this.database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; no sensitive context is emitted.
    }
  }

  // Returns the plaintext once, to the Owner only. It is not recoverable later.
  issue({ maxUses = 1, ttlMs = 7 * 24 * 60 * 60 * 1000, length = MIN_CODE_LENGTH } = {}) {
    if (!Number.isSafeInteger(maxUses) || maxUses < 1 || maxUses > MAX_USES) {
      throw new InviteCodeError("INVITE_MAX_USES_INVALID");
    }
    if (ttlMs !== null && (!Number.isSafeInteger(ttlMs) || ttlMs <= 0)) {
      throw new InviteCodeError("INVITE_TTL_INVALID");
    }
    const createdAt = this.#millis();
    const expiresAt = ttlMs === null ? null : createdAt + ttlMs;
    const code = generateCode(length);
    const result = this.database
      .prepare(
        `INSERT INTO invite_codes(
           code_hash, max_uses, used_count, expires_at, created_at
         ) VALUES (?, ?, 0, ?, ?)
         ON CONFLICT(code_hash) DO NOTHING`,
      )
      .run(hashCode(this.secret, code), maxUses, expiresAt, createdAt);
    if (Number(result.changes) !== 1) {
      throw new InviteCodeError("INVITE_CODE_COLLISION");
    }
    return Object.freeze({
      code,
      display: formatCode(code),
      maxUses,
      expiresAt,
      createdAt,
    });
  }

  // BEGIN IMMEDIATE plus a used_count < max_uses guard makes two concurrent
  // redemptions of a single-use code impossible.
  consume(code) {
    const codeHash = hashCode(this.secret, code);
    const now = this.#millis();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const row = this.database
        .prepare(
          `SELECT code_hash, max_uses, used_count, expires_at, disabled_at
           FROM invite_codes WHERE code_hash=?`,
        )
        .get(codeHash);
      if (
        !row ||
        row.disabled_at !== null ||
        (row.expires_at !== null && Number(row.expires_at) < now) ||
        Number(row.used_count) >= Number(row.max_uses)
      ) {
        throw new InviteCodeError("INVITE_INVALID");
      }
      const result = this.database
        .prepare(
          `UPDATE invite_codes
           SET used_count=used_count+1
           WHERE code_hash=? AND disabled_at IS NULL AND used_count < max_uses`,
        )
        .run(codeHash);
      if (Number(result.changes) !== 1) {
        throw new InviteCodeError("INVITE_INVALID");
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return Object.freeze({
      consumed: true,
      remainingUses: this.remainingUses(code),
    });
  }

  revoke(code) {
    const result = this.database
      .prepare(
        `UPDATE invite_codes SET disabled_at=?
         WHERE code_hash=? AND disabled_at IS NULL`,
      )
      .run(this.#millis(), hashCode(this.secret, code));
    return Number(result.changes) === 1;
  }

  remainingUses(code) {
    const row = this.database
      .prepare(
        "SELECT max_uses, used_count, disabled_at FROM invite_codes WHERE code_hash=?",
      )
      .get(hashCode(this.secret, code));
    if (!row || row.disabled_at !== null) {
      return 0;
    }
    return Math.max(0, Number(row.max_uses) - Number(row.used_count));
  }

  // Constant-time comparison so a caller cannot probe stored hashes by timing.
  matchesStoredHash(code, storedHash) {
    if (typeof storedHash !== "string" || storedHash.length !== 64) {
      return false;
    }
    const expected = Buffer.from(hashCode(this.secret, code), "utf8");
    const actual = Buffer.from(storedHash, "utf8");
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  }
}

module.exports = {
  CODE_ALPHABET,
  InviteCodeError,
  MAX_USES,
  MIN_CODE_LENGTH,
  SqliteInviteCodeStore,
  formatCode,
  generateCode,
  hashCode,
  normalizeCode,
};
