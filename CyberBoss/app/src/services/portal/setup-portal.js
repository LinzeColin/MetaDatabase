"use strict";

// CB-620 / AC-011: the portal request boundary. Every check fails closed —
// an unrecognised host, origin, action or oversized body is rejected before
// any handler runs, and the acting user always comes from the server-side
// session row rather than from the request.

const {
  SessionError,
  SqliteSessionTokenService,
  parseSessionCookie,
} = require("../security/session-token-service");
const {
  SetupTokenError,
  SqliteSetupTokenService,
} = require("../security/setup-token-service");
const { requireHttpsOrigin } = require("../security/secure-setup-link");

const MAX_BODY_BYTES = 16 * 1024;
// Frozen at CB-620. A portal request may only name one of these; anything
// else is rejected without reaching a handler.
const ACTION_ALLOWLIST = Object.freeze([
  "session.exchange",
  "session.logout",
  "provider.save",
  "provider.remove",
  "import.presign",
  "import.commit",
  "profile.decide",
  "privacy.export",
  "privacy.delete",
]);
const MUTATING_METHODS = Object.freeze(["POST", "PUT", "PATCH", "DELETE"]);
// session.exchange is the one action that runs before a session exists: it
// trades a single-use setup token for one. It is CSRF-exempt because it
// carries no ambient credential — the setup token itself is the proof.
const PRE_SESSION_ACTIONS = Object.freeze(["session.exchange"]);

class PortalError extends Error {
  constructor(code, status) {
    super(code);
    this.name = "PortalError";
    this.code = code;
    this.status = status;
  }
}

function normalizeAllowedOrigins(origins) {
  if (!Array.isArray(origins) || origins.length === 0) {
    throw new PortalError("PORTAL_ORIGIN_ALLOWLIST_REQUIRED", 500);
  }
  return Object.freeze(origins.map((origin) => requireHttpsOrigin(origin)));
}

function hostsFromOrigins(origins) {
  return Object.freeze(origins.map((origin) => new URL(origin).host));
}

function bodyByteLength(body) {
  if (body === null || body === undefined) {
    return 0;
  }
  if (Buffer.isBuffer(body)) {
    return body.length;
  }
  if (typeof body === "string") {
    return Buffer.byteLength(body, "utf8");
  }
  throw new PortalError("PORTAL_BODY_TYPE_INVALID", 400);
}

class SetupPortal {
  constructor({
    database,
    allowedOrigins,
    sessionService = null,
    setupTokenService = null,
    userRepository = null,
    handlers = {},
    now = () => Date.now(),
  }) {
    this.allowedOrigins = normalizeAllowedOrigins(allowedOrigins);
    this.allowedHosts = hostsFromOrigins(this.allowedOrigins);
    this.sessions =
      sessionService || new SqliteSessionTokenService({ database, now });
    this.setupTokens =
      setupTokenService || new SqliteSetupTokenService({ database, now });
    this.users = userRepository;
    this.handlers = handlers;
  }

  // Exact-match only: no suffix or wildcard comparison, so evil-example.com
  // can never satisfy an allowlist entry of example.com.
  #assertOrigin(headers) {
    const origin = headers.origin || headers.Origin || null;
    if (typeof origin !== "string" || !this.allowedOrigins.includes(origin)) {
      throw new PortalError("ORIGIN_NOT_ALLOWED", 403);
    }
  }

  #assertHost(headers) {
    const host = headers.host || headers.Host || null;
    if (typeof host !== "string" || !this.allowedHosts.includes(host)) {
      throw new PortalError("HOST_NOT_ALLOWED", 403);
    }
  }

  #assertAction(action) {
    if (typeof action !== "string" || !ACTION_ALLOWLIST.includes(action)) {
      throw new PortalError("ACTION_NOT_ALLOWED", 403);
    }
  }

  #assertBodySize(body) {
    if (bodyByteLength(body) > MAX_BODY_BYTES) {
      throw new PortalError("BODY_TOO_LARGE", 413);
    }
  }

  #parseBody(body) {
    if (body === null || body === undefined || body === "") {
      return {};
    }
    const text = Buffer.isBuffer(body) ? body.toString("utf8") : body;
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new PortalError("BODY_NOT_JSON", 400);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new PortalError("BODY_NOT_OBJECT", 400);
    }
    return parsed;
  }

  handle({ method, action, headers = {}, body = null }) {
    if (typeof method !== "string" || !MUTATING_METHODS.includes(method)) {
      throw new PortalError("METHOD_NOT_ALLOWED", 405);
    }
    // Size first: an oversized body is rejected before it is parsed at all.
    this.#assertBodySize(body);
    this.#assertHost(headers);
    this.#assertOrigin(headers);
    this.#assertAction(action);
    const payload = this.#parseBody(body);

    if (PRE_SESSION_ACTIONS.includes(action)) {
      return this.#exchangeSetupToken(payload);
    }

    const cookie = parseSessionCookie(headers.cookie || headers.Cookie || "");
    if (!cookie) {
      throw new PortalError("SESSION_INVALID", 401);
    }
    let session;
    try {
      session = this.sessions.verify({
        token: cookie,
        csrf: headers["x-csrf-token"] || headers["X-CSRF-Token"] || null,
        requireCsrf: true,
      });
    } catch (error) {
      throw new PortalError(
        error instanceof SessionError ? error.code : "SESSION_INVALID",
        error instanceof SessionError && error.code === "CSRF_INVALID" ? 403 : 401,
      );
    }

    // The acting user is the session's user. A user_id in the body is ignored,
    // and is treated as an attack if it disagrees.
    if (
      typeof payload.user_id === "string" &&
      payload.user_id !== session.userId
    ) {
      throw new PortalError("USER_SCOPE_VIOLATION", 403);
    }
    if (this.users && !this.users.getById(session.userId)) {
      throw new PortalError("USER_NOT_FOUND", 401);
    }

    const handler = this.handlers[action];
    if (typeof handler !== "function") {
      throw new PortalError("ACTION_NOT_IMPLEMENTED", 501);
    }
    const { user_id: _ignored, ...safePayload } = payload;
    return handler({ userId: session.userId, payload: safePayload });
  }

  #exchangeSetupToken(payload) {
    const { token, purpose } = payload;
    let consumed;
    try {
      consumed = this.setupTokens.consume({ token, purpose });
    } catch (error) {
      throw new PortalError(
        error instanceof SetupTokenError ? error.code : "LINK_INVALID",
        401,
      );
    }
    const session = this.sessions.issue({ userId: consumed.userId });
    return Object.freeze({
      status: 200,
      userId: consumed.userId,
      purpose: consumed.purpose,
      csrf: session.csrf,
      setCookie: session.cookie,
      expiresAt: session.expiresAt,
    });
  }

  // AC-011: one WeChat command revokes every session and outstanding link.
  revokeEverythingForUser(userId) {
    return Object.freeze({
      sessionsRevoked: this.sessions.revokeAllForUser(userId),
      setupLinksRevoked: this.setupTokens.revokeAllForUser(userId),
    });
  }
}

module.exports = {
  ACTION_ALLOWLIST,
  MAX_BODY_BYTES,
  MUTATING_METHODS,
  PRE_SESSION_ACTIONS,
  PortalError,
  SetupPortal,
};
