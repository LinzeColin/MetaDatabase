"use strict";

// CB-620 / AC-010: a setup link carries a 10-minute, single-use, opaque token.
// Only its SHA-256 hash is stored, so a database or backup read cannot replay
// a link, and a second consumption of the same token always fails.

const { createHash, randomBytes, timingSafeEqual } = require("node:crypto");

const DEFAULT_TTL_MS = 10 * 60 * 1000;
const MAX_TTL_MS = 10 * 60 * 1000;
const PURPOSES = Object.freeze(["provider", "import", "profile", "privacy"]);
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,86}$/;

class SetupTokenError extends Error {
  constructor(code) {
    super(code);
    this.name = "SetupTokenError";
    this.code = code;
  }
}

function hashToken(token) {
  if (typeof token !== "string" || !TOKEN_PATTERN.test(token)) {
    throw new SetupTokenError("LINK_INVALID");
  }
  return createHash("sha256").update(token, "utf8").digest("hex");
}

class SqliteSetupTokenService {
  constructor({ database, now = () => Date.now(), ttlMs = DEFAULT_TTL_MS }) {
    if (!database || typeof database.prepare !== "function") {
      throw new SetupTokenError("DATABASE_REQUIRED");
    }
    if (!Number.isSafeInteger(ttlMs) || ttlMs <= 0 || ttlMs > MAX_TTL_MS) {
      throw new SetupTokenError("SETUP_TOKEN_TTL_INVALID");
    }
    this.database = database;
    this.now = now;
    this.ttlMs = ttlMs;
  }

  #millis() {
    const value = this.now();
    const millis = value instanceof Date ? value.getTime() : Number(value);
    if (!Number.isFinite(millis)) {
      throw new SetupTokenError("CLOCK_INVALID");
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

  // The plaintext token is returned once and never persisted or logged.
  issue({ userId, purpose }) {
    if (!PURPOSES.includes(purpose)) {
      throw new SetupTokenError("SETUP_PURPOSE_INVALID");
    }
    const createdAt = this.#millis();
    const expiresAt = createdAt + this.ttlMs;
    const token = randomBytes(32).toString("base64url");
    const result = this.database
      .prepare(
        `INSERT INTO setup_tokens(
           token_hash, user_id, purpose, expires_at, used_at, created_at
         ) VALUES (?, ?, ?, ?, NULL, ?)
         ON CONFLICT(token_hash) DO NOTHING`,
      )
      .run(hashToken(token), userId, purpose, expiresAt, createdAt);
    if (Number(result.changes) !== 1) {
      throw new SetupTokenError("SETUP_TOKEN_COLLISION");
    }
    return Object.freeze({ token, purpose, expiresAt, ttlMs: this.ttlMs });
  }

  // BEGIN IMMEDIATE plus a used_at IS NULL guard makes concurrent replay of a
  // single-use link impossible; expiry and purpose mismatch fail closed.
  consume({ token, purpose }) {
    if (!PURPOSES.includes(purpose)) {
      throw new SetupTokenError("SETUP_PURPOSE_INVALID");
    }
    const tokenHash = hashToken(token);
    const now = this.#millis();
    this.database.exec("BEGIN IMMEDIATE");
    let row;
    try {
      row = this.database
        .prepare(
          `SELECT token_hash, user_id, purpose, expires_at, used_at
           FROM setup_tokens WHERE token_hash=?`,
        )
        .get(tokenHash);
      if (!row || row.used_at !== null || row.purpose !== purpose) {
        throw new SetupTokenError("LINK_INVALID");
      }
      if (Number(row.expires_at) < now) {
        throw new SetupTokenError("LINK_EXPIRED");
      }
      const updated = this.database
        .prepare(
          "UPDATE setup_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL",
        )
        .run(now, tokenHash);
      if (Number(updated.changes) !== 1) {
        throw new SetupTokenError("LINK_INVALID");
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return Object.freeze({
      userId: row.user_id,
      purpose: row.purpose,
      consumedAt: now,
    });
  }

  // Called when a user revokes access from WeChat: every outstanding link dies.
  revokeAllForUser(userId) {
    const now = this.#millis();
    return Number(
      this.database
        .prepare(
          "UPDATE setup_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
        )
        .run(now, userId).changes,
    );
  }

  purgeExpired() {
    return Number(
      this.database
        .prepare("DELETE FROM setup_tokens WHERE expires_at < ?")
        .run(this.#millis()).changes,
    );
  }

  matchesStoredHash(token, storedHash) {
    if (typeof storedHash !== "string" || storedHash.length !== 64) {
      return false;
    }
    const expected = Buffer.from(hashToken(token), "utf8");
    const actual = Buffer.from(storedHash, "utf8");
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  }
}

module.exports = {
  DEFAULT_TTL_MS,
  MAX_TTL_MS,
  PURPOSES,
  SetupTokenError,
  SqliteSetupTokenService,
  hashToken,
};
