"use strict";

// 后台登录票：主人在微信里发「后台」，机器人回一条一次性链接。
//
// 存在的理由是一句用户原话：「我不可能每次都有 token」。后台链接里那串管理员
// 令牌是**长期**凭据——要人记住它、保存它、每次粘贴它，是把服务器的钥匙交给
// 剪贴板保管。而主人手上永远有的东西是微信本身。
//
// 所以：微信里要一次，拿一条 5 分钟、只能用一次的链接；点开就换成会话 cookie，
// 票当场作废。长期令牌一次都不经过聊天记录。
//
// 只存哈希。这张表被人看到也换不出可用的链接。

const { createHash, randomBytes, timingSafeEqual } = require("node:crypto");

const DEFAULT_TTL_MS = 5 * 60_000;
const MAX_TTL_MS = 30 * 60_000;
// 和 session/setup 令牌同一个字符集与长度下限，方便一眼看出这是同一类东西。
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,86}$/;

class AdminTicketError extends Error {
  constructor(code) {
    super(code);
    this.name = "AdminTicketError";
    this.code = code;
  }
}

function hashToken(token) {
  return createHash("sha256").update(String(token), "utf8").digest("hex");
}

function constantTimeEquals(left, right) {
  const a = Buffer.from(String(left), "utf8");
  const b = Buffer.from(String(right), "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

class SqliteAdminLoginTickets {
  constructor({ database, now = () => Date.now(), ttlMs = DEFAULT_TTL_MS }) {
    if (!database || typeof database.prepare !== "function") {
      throw new AdminTicketError("DATABASE_REQUIRED");
    }
    if (!Number.isSafeInteger(ttlMs) || ttlMs <= 0 || ttlMs > MAX_TTL_MS) {
      throw new AdminTicketError("TICKET_TTL_INVALID");
    }
    this.database = database;
    this.now = now;
    this.ttlMs = ttlMs;
  }

  #millis() {
    const value = this.now();
    const millis = value instanceof Date ? value.getTime() : Number(value);
    if (!Number.isFinite(millis)) {
      throw new AdminTicketError("CLOCK_INVALID");
    }
    return Math.trunc(millis);
  }

  issue() {
    const createdAt = this.#millis();
    const token = randomBytes(32).toString("base64url");
    const result = this.database
      .prepare(
        `INSERT INTO admin_login_tickets(token_hash, expires_at, used_at, created_at)
         VALUES (?, ?, NULL, ?)
         ON CONFLICT(token_hash) DO NOTHING`,
      )
      .run(hashToken(token), createdAt + this.ttlMs, createdAt);
    if (Number(result.changes) !== 1) {
      throw new AdminTicketError("TICKET_COLLISION");
    }
    // 顺手清掉过期的。这张表本来就该是空的绝大多数时候。
    this.database
      .prepare("DELETE FROM admin_login_tickets WHERE expires_at < ?")
      .run(createdAt);
    return Object.freeze({ token, expiresAt: createdAt + this.ttlMs, ttlMs: this.ttlMs });
  }

  // 一次性：把标记已用和判定放进同一个事务里，两个人同时点同一条链接时只有
  // 一个能成。判定失败一律回同一个错误码——不区分"没这张票"和"用过了"，
  // 免得能被拿来试探哪些票存在过。
  consume(token) {
    if (typeof token !== "string" || !TOKEN_PATTERN.test(token)) {
      throw new AdminTicketError("TICKET_INVALID");
    }
    const nowMs = this.#millis();
    const tokenHash = hashToken(token);
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const row = this.database
        .prepare(
          "SELECT token_hash, expires_at, used_at FROM admin_login_tickets WHERE token_hash=?",
        )
        .get(tokenHash);
      if (
        !row
        || row.used_at !== null
        || Number(row.expires_at) <= nowMs
        || !constantTimeEquals(row.token_hash, tokenHash)
      ) {
        this.database.exec("ROLLBACK");
        throw new AdminTicketError("TICKET_INVALID");
      }
      const result = this.database
        .prepare(
          "UPDATE admin_login_tickets SET used_at=? WHERE token_hash=? AND used_at IS NULL",
        )
        .run(nowMs, tokenHash);
      if (Number(result.changes) !== 1) {
        this.database.exec("ROLLBACK");
        throw new AdminTicketError("TICKET_INVALID");
      }
      this.database.exec("COMMIT");
      return Object.freeze({ consumedAt: nowMs });
    } catch (error) {
      try {
        this.database.exec("ROLLBACK");
      } catch {
        // 已经 rollback 过了。
      }
      throw error;
    }
  }
}

module.exports = {
  AdminTicketError,
  DEFAULT_TTL_MS,
  MAX_TTL_MS,
  SqliteAdminLoginTickets,
  hashToken,
};
