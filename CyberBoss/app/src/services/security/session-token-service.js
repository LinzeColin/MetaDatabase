"use strict";

// CB-620 / AC-011: the portal session is short-lived, server-owned and
// revocable from WeChat. The cookie is Secure + HttpOnly + SameSite=Strict and
// every mutating request must also present the matching CSRF token, so a
// cross-site page cannot act even if a cookie were somehow attached.

const { createHash, randomBytes, timingSafeEqual } = require("node:crypto");

const DEFAULT_TTL_MS = 30 * 60 * 1000;
const MAX_TTL_MS = 24 * 60 * 60 * 1000;
const COOKIE_NAME = "cb_session";
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,86}$/;

class SessionError extends Error {
  constructor(code) {
    super(code);
    this.name = "SessionError";
    this.code = code;
  }
}

function sha256(value) {
  if (typeof value !== "string" || !TOKEN_PATTERN.test(value)) {
    throw new SessionError("SESSION_INVALID");
  }
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function constantTimeEquals(left, right) {
  if (
    typeof left !== "string" ||
    typeof right !== "string" ||
    left.length !== right.length
  ) {
    return false;
  }
  return timingSafeEqual(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));
}

class SqliteSessionTokenService {
  constructor({ database, now = () => Date.now(), ttlMs = DEFAULT_TTL_MS }) {
    if (!database || typeof database.prepare !== "function") {
      throw new SessionError("DATABASE_REQUIRED");
    }
    if (!Number.isSafeInteger(ttlMs) || ttlMs <= 0 || ttlMs > MAX_TTL_MS) {
      throw new SessionError("SESSION_TTL_INVALID");
    }
    this.database = database;
    this.now = now;
    this.ttlMs = ttlMs;
  }

  #millis() {
    const value = this.now();
    const millis = value instanceof Date ? value.getTime() : Number(value);
    if (!Number.isFinite(millis)) {
      throw new SessionError("CLOCK_INVALID");
    }
    return Math.trunc(millis);
  }

  issue({ userId }) {
    const createdAt = this.#millis();
    const expiresAt = createdAt + this.ttlMs;
    const token = randomBytes(32).toString("base64url");
    const csrf = randomBytes(32).toString("base64url");
    const result = this.database
      .prepare(
        `INSERT INTO web_sessions(
           token_hash, csrf_hash, user_id, expires_at, revoked_at, created_at
         ) VALUES (?, ?, ?, ?, NULL, ?)
         ON CONFLICT(token_hash) DO NOTHING`,
      )
      .run(sha256(token), sha256(csrf), userId, expiresAt, createdAt);
    if (Number(result.changes) !== 1) {
      throw new SessionError("SESSION_COLLISION");
    }
    return Object.freeze({
      token,
      csrf,
      expiresAt,
      cookie: this.cookieHeader(token),
    });
  }

  cookieHeader(token) {
    return [
      `${COOKIE_NAME}=${token}`,
      "Path=/",
      "HttpOnly",
      "Secure",
      "SameSite=Strict",
      `Max-Age=${Math.floor(this.ttlMs / 1000)}`,
    ].join("; ");
  }

  clearCookieHeader() {
    return [
      `${COOKIE_NAME}=`,
      "Path=/",
      "HttpOnly",
      "Secure",
      "SameSite=Strict",
      "Max-Age=0",
    ].join("; ");
  }

  // The user id comes from the stored row, never from the request body, so a
  // caller cannot act as another user by editing a form field.
  verify({ token, csrf = null, requireCsrf = true }) {
    const row = this.database
      .prepare(
        `SELECT token_hash, csrf_hash, user_id, expires_at, revoked_at
         FROM web_sessions WHERE token_hash=?`,
      )
      .get(sha256(token));
    if (!row || row.revoked_at !== null) {
      throw new SessionError("SESSION_INVALID");
    }
    if (Number(row.expires_at) < this.#millis()) {
      throw new SessionError("SESSION_EXPIRED");
    }
    // A missing or malformed CSRF token is a CSRF failure, not a session
    // failure: the session itself was valid, the request just was not proved.
    if (requireCsrf) {
      let presented = null;
      try {
        presented = sha256(String(csrf));
      } catch {
        throw new SessionError("CSRF_INVALID");
      }
      if (!constantTimeEquals(presented, row.csrf_hash)) {
        throw new SessionError("CSRF_INVALID");
      }
    }
    return Object.freeze({ userId: row.user_id, expiresAt: Number(row.expires_at) });
  }

  revoke(token) {
    return (
      Number(
        this.database
          .prepare(
            "UPDATE web_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
          )
          .run(this.#millis(), sha256(token)).changes,
      ) === 1
    );
  }

  // AC-011: one WeChat command kills every web session the user has anywhere.
  revokeAllForUser(userId) {
    return Number(
      this.database
        .prepare(
          "UPDATE web_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
        )
        .run(this.#millis(), userId).changes,
    );
  }

  activeSessionCount(userId) {
    return Number(
      this.database
        .prepare(
          `SELECT COUNT(*) AS count FROM web_sessions
           WHERE user_id=? AND revoked_at IS NULL AND expires_at >= ?`,
        )
        .get(userId, this.#millis()).count,
    );
  }

  purgeExpired() {
    return Number(
      this.database
        .prepare("DELETE FROM web_sessions WHERE expires_at < ?")
        .run(this.#millis()).changes,
    );
  }
}

function parseSessionCookie(header) {
  if (typeof header !== "string" || header.length > 4096) {
    return null;
  }
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === COOKIE_NAME) {
      const value = rest.join("=");
      return TOKEN_PATTERN.test(value) ? value : null;
    }
  }
  return null;
}

module.exports = {
  COOKIE_NAME,
  DEFAULT_TTL_MS,
  MAX_TTL_MS,
  SessionError,
  SqliteSessionTokenService,
  parseSessionCookie,
};
