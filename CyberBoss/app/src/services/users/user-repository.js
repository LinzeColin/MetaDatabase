"use strict";

// CB-610 / AC-003, AC-005: the identity store behind "one bot, many isolated
// users". Two senders on the same bot account resolve to two distinct
// user_ids with independent state; the channel principal is only ever stored
// as a keyed hash.

const {
  UserIdentityError,
  deriveUserIdentity,
  requireUserId,
} = require("./user-identity");

const ROLES = Object.freeze(["owner", "user"]);
const STATUSES = Object.freeze([
  "pending_consent",
  "active",
  "suspended",
  "deleting",
  "deleted",
]);
const MODEL_ELIGIBLE_STATUSES = Object.freeze(["active"]);

class UserRepositoryError extends Error {
  constructor(code) {
    super(code);
    this.name = "UserRepositoryError";
    this.code = code;
  }
}

function freezeRow(row) {
  return row ? Object.freeze({ ...row }) : null;
}

class SqliteUserRepository {
  constructor({ database, identityKey, now = () => new Date() }) {
    if (!database || typeof database.prepare !== "function") {
      throw new UserRepositoryError("DATABASE_REQUIRED");
    }
    if (!Buffer.isBuffer(identityKey) || identityKey.length < 32) {
      throw new UserRepositoryError("IDENTITY_KEY_MUST_BE_AT_LEAST_32_BYTES");
    }
    this.database = database;
    this.identityKey = identityKey;
    this.now = now;
  }

  #timestamp() {
    const value = this.now();
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) {
      throw new UserRepositoryError("CLOCK_INVALID");
    }
    return date.toISOString();
  }

  #rollbackQuietly() {
    try {
      this.database.exec("ROLLBACK");
    } catch {
      // A commit may already have completed; no sensitive context is emitted.
    }
  }

  identify({ channel = "weixin", botAccountRef, senderRef }) {
    return deriveUserIdentity({
      identityKey: this.identityKey,
      channel,
      botAccountRef,
      senderRef,
    });
  }

  // 还在用的普通用户有几个。主人不算——他不占席位。
  //
  // 开放模式下这是唯一挡住"任何扫到码的人都来烧主人额度"的数，所以它数的是
  // active，不是全部：被暂停或已注销的人腾出来的位子应当能给新人用。
  countActiveOrdinaryUsers() {
    const row = this.database
      .prepare("SELECT COUNT(*) AS c FROM users WHERE role='user' AND status='active'")
      .get();
    return Number(row?.c || 0);
  }

  resolveByPrincipal({ channel = "weixin", botAccountRef, senderRef }) {
    const identity = this.identify({ channel, botAccountRef, senderRef });
    const row = this.database
      .prepare(
        `SELECT u.user_id, u.role, u.status, u.consent_version, u.consented_at,
                u.created_at, u.updated_at, c.channel, c.principal_hash
         FROM user_channels c
         JOIN users u ON u.user_id = c.user_id
         WHERE c.channel=? AND c.bot_account_ref=? AND c.principal_hash=?
           AND c.revoked_at IS NULL`,
      )
      .get(identity.channel, botAccountRef, identity.principalHash);
    return row ? Object.freeze({ ...row, derivedUserId: identity.userId }) : null;
  }

  // A first-contact sender only ever reaches the minimal pending state; no
  // model call is possible until consent moves the row to active.
  ensurePending({
    channel = "weixin",
    botAccountRef,
    senderRef,
    role = "user",
    principalCiphertext = null,
  }) {
    if (!ROLES.includes(role)) {
      throw new UserRepositoryError("ROLE_INVALID");
    }
    const identity = this.identify({ channel, botAccountRef, senderRef });
    const status = role === "owner" ? "active" : "pending_consent";
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(
          `INSERT INTO users(
             user_id, role, status, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO NOTHING`,
        )
        .run(identity.userId, role, status, now, now);
      this.database
        .prepare(
          `INSERT INTO user_channels(
             channel, bot_account_ref, principal_hash, user_id,
             principal_ciphertext, created_at
           ) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(channel, bot_account_ref, principal_hash)
           DO UPDATE SET revoked_at=NULL`,
        )
        .run(
          identity.channel,
          botAccountRef,
          identity.principalHash,
          identity.userId,
          principalCiphertext,
          now,
        );
      this.database
        .prepare(
          `INSERT INTO user_settings(user_id, locale, checkin_enabled, updated_at)
           VALUES (?, 'zh-CN', 0, ?)
           ON CONFLICT(user_id) DO NOTHING`,
        )
        .run(identity.userId, now);
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return this.getById(identity.userId);
  }

  activateConsent({ userId, policyVersion, scope = "core" }) {
    requireUserId(userId);
    if (typeof policyVersion !== "string" || policyVersion.length === 0) {
      throw new UserRepositoryError("POLICY_VERSION_REQUIRED");
    }
    const now = this.#timestamp();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = this.database
        .prepare(
          `UPDATE users
           SET status='active', consent_version=?, consented_at=?, updated_at=?
           WHERE user_id=? AND status='pending_consent'`,
        )
        .run(policyVersion, now, now, userId);
      if (Number(result.changes) !== 1) {
        throw new UserRepositoryError("CONSENT_STATE_INVALID");
      }
      this.database
        .prepare(
          `INSERT INTO consent_events(
             event_id, user_id, policy_version, scope, decision, occurred_at
           ) VALUES (?, ?, ?, ?, 'granted', ?)`,
        )
        .run(
          `consent_${userId}_${policyVersion}_${now}`,
          userId,
          policyVersion,
          scope,
          now,
        );
      this.database.exec("COMMIT");
    } catch (error) {
      this.#rollbackQuietly();
      throw error;
    }
    return this.getById(userId);
  }

  setStatus(userId, status) {
    requireUserId(userId);
    if (!STATUSES.includes(status) || status === "deleted") {
      throw new UserRepositoryError("STATUS_INVALID");
    }
    const now = this.#timestamp();
    const result = this.database
      .prepare(
        `UPDATE users SET status=?, updated_at=?
         WHERE user_id=? AND status<>'deleted'`,
      )
      .run(status, now, userId);
    if (Number(result.changes) !== 1) {
      throw new UserRepositoryError("USER_STATE_INVALID");
    }
    return this.getById(userId);
  }

  getById(userId) {
    requireUserId(userId);
    return freezeRow(
      this.database
        .prepare(
          `SELECT user_id, role, status, consent_version, consented_at,
                  created_at, updated_at
           FROM users WHERE user_id=?`,
        )
        .get(userId),
    );
  }

  getSettings(userId) {
    requireUserId(userId);
    return freezeRow(
      this.database
        .prepare(
          `SELECT user_id, provider_id, model_id, locale, timezone,
                  checkin_enabled, updated_at
           FROM user_settings WHERE user_id=?`,
        )
        .get(userId),
    );
  }

  isOwner(userId) {
    const row = this.getById(userId);
    return Boolean(row) && row.role === "owner";
  }

  // AC-004 / AC-041: the single gate every model call must pass. Pending,
  // suspended, deleting and deleted users are all denied.
  mayCallModel(userId) {
    const row = this.getById(userId);
    return Boolean(row) && MODEL_ELIGIBLE_STATUSES.includes(row.status);
  }

  countByRole(role) {
    if (!ROLES.includes(role)) {
      throw new UserRepositoryError("ROLE_INVALID");
    }
    return Number(
      this.database
        .prepare("SELECT COUNT(*) AS count FROM users WHERE role=?")
        .get(role).count,
    );
  }

  bindOwnerChannel({ userId, channel = "weixin", botAccountRef, senderRef }) {
    requireUserId(userId);
    const identity = this.identify({ channel, botAccountRef, senderRef });
    if (identity.userId !== userId && !this.isOwner(userId)) {
      throw new UserRepositoryError("OWNER_BINDING_FORBIDDEN");
    }
    const now = this.#timestamp();
    this.database
      .prepare(
        `INSERT INTO user_channels(
           channel, bot_account_ref, principal_hash, user_id, created_at
         ) VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(channel, bot_account_ref, principal_hash)
         DO UPDATE SET revoked_at=NULL`,
      )
      .run(
        identity.channel,
        botAccountRef,
        identity.principalHash,
        userId,
        now,
      );
    return identity;
  }
}

module.exports = {
  MODEL_ELIGIBLE_STATUSES,
  ROLES,
  STATUSES,
  SqliteUserRepository,
  UserIdentityError,
  UserRepositoryError,
};
