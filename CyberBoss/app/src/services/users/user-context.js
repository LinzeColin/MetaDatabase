"use strict";

// CB-630 / AC-006: the server-owned UserContext. It is built only at a trusted
// ingress from an already-resolved user row, is frozen, and carries the single
// capability decision every downstream component consults. Nothing in a
// message body can construct or widen one.

const { USER_ID_PATTERN } = require("./user-identity");

const ROLES = Object.freeze(["owner", "user"]);
const STATUSES = Object.freeze([
  "pending_consent",
  "active",
  "suspended",
  "deleting",
  "deleted",
]);

// Capabilities only the Owner may ever reach. An ordinary user touching any of
// these is a hard failure, never a downgrade or a silent no-op.
const OWNER_ONLY_CAPABILITIES = Object.freeze([
  "codex.turn",
  "claudecode.turn",
  "workspace.read",
  "workspace.write",
  "shell.execute",
  "project.tool",
  "mcp.invoke",
  "ops.manage",
  "release.manage",
  "invite.issue",
  "status.internal",
]);

// Capabilities an ordinary active user may reach. The two sets are disjoint by
// construction and that is asserted by the CB-630 suite.
const USER_CAPABILITIES = Object.freeze([
  "chat.turn",
  "import.upload",
  "profile.read",
  "profile.decide",
  "timeline.read",
  "diary.write",
  "reminder.manage",
  "privacy.export",
  "privacy.delete",
  "provider.manage",
]);

class UserContextError extends Error {
  constructor(code) {
    super(code);
    this.name = "UserContextError";
    this.code = code;
  }
}

class UserContext {
  constructor({
    userId,
    role = "user",
    status = "active",
    channel = "weixin",
    principalHash = null,
    botAccountRef = null,
  }) {
    if (typeof userId !== "string" || !USER_ID_PATTERN.test(userId)) {
      throw new UserContextError("USER_CONTEXT_ID_INVALID");
    }
    if (!ROLES.includes(role)) {
      throw new UserContextError("USER_CONTEXT_ROLE_INVALID");
    }
    if (!STATUSES.includes(status)) {
      throw new UserContextError("USER_CONTEXT_STATUS_INVALID");
    }
    this.userId = userId;
    this.role = role;
    this.status = status;
    this.channel = channel;
    this.principalHash = principalHash;
    this.botAccountRef = botAccountRef;
    Object.freeze(this);
  }

  get isOwner() {
    return this.role === "owner";
  }

  requireActive() {
    if (this.status !== "active") {
      throw new UserContextError("USER_NOT_ACTIVE");
    }
    return this;
  }

  requireOwner() {
    this.requireActive();
    if (!this.isOwner) {
      throw new UserContextError("OWNER_ONLY");
    }
    return this;
  }

  // The single authority for AC-006. Unknown capabilities fail closed.
  may(capability) {
    if (this.status !== "active") {
      return false;
    }
    if (OWNER_ONLY_CAPABILITIES.includes(capability)) {
      return this.isOwner;
    }
    if (USER_CAPABILITIES.includes(capability)) {
      return true;
    }
    return false;
  }

  requireCapability(capability) {
    if (!this.may(capability)) {
      throw new UserContextError(
        OWNER_ONLY_CAPABILITIES.includes(capability)
          ? "OWNER_ONLY_CAPABILITY"
          : this.status !== "active"
            ? "USER_NOT_ACTIVE"
            : "CAPABILITY_NOT_ALLOWED",
      );
    }
    return this;
  }

  // Cross-user access is refused rather than filtered, so an IDOR attempt is
  // visible in the logs instead of silently returning nothing.
  requireOwnRecord(record, userColumn = "user_id") {
    if (!record || record[userColumn] !== this.userId) {
      throw new UserContextError("USER_SCOPE_VIOLATION");
    }
    return record;
  }

  toRedactedJson() {
    // Deliberately omits user_id and principal_hash: this shape is safe for
    // Status and logs, which must never carry a user identifier.
    return Object.freeze({
      role: this.role,
      status: this.status,
      channel: this.channel,
    });
  }
}

// Trusted ingress: the context is derived from a stored user row that the
// server resolved from the bot account and sender, never from request input.
function buildUserContextFromRow(row, { channel = "weixin", botAccountRef = null } = {}) {
  if (!row || typeof row !== "object") {
    throw new UserContextError("USER_NOT_FOUND");
  }
  return new UserContext({
    userId: row.user_id,
    role: row.role,
    status: row.status,
    channel,
    principalHash: row.principal_hash || null,
    botAccountRef,
  });
}

function resolveServerOwnedUserContext({
  userRepository,
  channel = "weixin",
  botAccountRef,
  senderRef,
}) {
  if (!botAccountRef || !senderRef) {
    throw new UserContextError("PRINCIPAL_REQUIRED");
  }
  const row = userRepository.resolveByPrincipal({
    channel,
    botAccountRef,
    senderRef,
  });
  if (!row) {
    throw new UserContextError("USER_NOT_FOUND");
  }
  return buildUserContextFromRow(row, { channel, botAccountRef });
}

module.exports = {
  OWNER_ONLY_CAPABILITIES,
  ROLES,
  STATUSES,
  USER_CAPABILITIES,
  UserContext,
  UserContextError,
  buildUserContextFromRow,
  resolveServerOwnedUserContext,
};
