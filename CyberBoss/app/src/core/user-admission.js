"use strict";

// Anchor-based integration for the v0.0.0.8 overlay (machine/overlay_map.json
// declares strategy `additive_overlay_then_anchor_based_integration`). The
// additive half — identity, registration, UserContext — was built and proved at
// CB-610/CB-620/CB-630. This module is the anchor: it is the one place where a
// real inbound WeChat message is turned into a server-owned UserContext before
// anything else in the turn runs.
//
// Everything here is decided from the bot account and the sender the channel
// resolved. Nothing in a message body can name a user, widen a role or skip a
// state — the text is only ever compared against the frozen Chinese commands.

const { createHmac } = require("node:crypto");

const { SqliteInviteCodeStore } = require("../services/users/invite-code-store");
const { ACTIONS, COMMANDS, MESSAGES } = require("../services/users/onboarding-state");
const {
  DEFAULT_POLICY_VERSION,
  RegistrationService,
} = require("../services/users/registration-service");
const { SqliteUserRepository } = require("../services/users/user-repository");
const {
  UserContextError,
  buildUserContextFromRow,
} = require("../services/users/user-context");

// An invite code is consumed by exact match, so a message that is one of the
// frozen commands is never spent as a code by mistake.
const RESERVED_INPUTS = Object.freeze(Object.values(COMMANDS));
const INVITE_CANDIDATE = /^[A-Za-z0-9-]{8,64}$/;

class UserAdmissionError extends Error {
  constructor(code) {
    super(code);
    this.name = "UserAdmissionError";
    this.code = code;
  }
}

function deriveSubKey(key, info) {
  return createHmac("sha256", key).update(info).digest();
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeSenderList(value) {
  return Object.freeze(
    (Array.isArray(value) ? value : [])
      .map((entry) => normalizeText(entry))
      .filter(Boolean),
  );
}

function reply(action, extra = {}) {
  return Object.freeze({
    route: "reply",
    action,
    text: MESSAGES[action],
    modelCalls: 0,
    ...extra,
  });
}

class UserAdmissionService {
  constructor({
    database,
    identityKey,
    ownerUserId,
    ownerSenderIds = [],
    channel = "weixin",
    registrationMode = "invite",
    policyVersion = DEFAULT_POLICY_VERSION,
    now = () => new Date(),
  }) {
    if (!database || typeof database.prepare !== "function") {
      throw new UserAdmissionError("DATABASE_REQUIRED");
    }
    if (!Buffer.isBuffer(identityKey) || identityKey.length < 32) {
      throw new UserAdmissionError("IDENTITY_KEY_REQUIRED");
    }
    if (typeof ownerUserId !== "string" || !ownerUserId) {
      throw new UserAdmissionError("OWNER_USER_ID_REQUIRED");
    }
    this.channel = channel;
    this.ownerUserId = ownerUserId;
    this.ownerSenderIds = normalizeSenderList(ownerSenderIds);
    this.users = new SqliteUserRepository({ database, identityKey, now });
    this.invites =
      registrationMode === "invite"
        ? new SqliteInviteCodeStore({
            database,
            // Derived rather than stored: the invite secret is a function of the
            // owner-only identity key, so it is stable across restarts and adds
            // no new secret file to the host.
            secret: deriveSubKey(identityKey, "cyberboss-invite-code-secret"),
          })
        : null;
    this.registration = new RegistrationService({
      userRepository: this.users,
      inviteStore: this.invites,
      registrationMode,
      policyVersion,
    });
  }

  isOwnerSender(senderRef) {
    // An empty owner list means this deployment has not named an Owner sender,
    // so no inbound sender is ever treated as the Owner. Failing closed here is
    // what keeps "unknown sender" from inheriting Owner capabilities.
    return this.ownerSenderIds.includes(normalizeText(senderRef));
  }

  // The Owner's WeChat principal is bound to the server-derived Owner user id on
  // first contact. The binding is idempotent and is the only way a principal
  // ever reaches the `owner` role.
  #admitOwner({ botAccountRef, senderRef }) {
    this.users.bindOwnerChannel({
      userId: this.ownerUserId,
      channel: this.channel,
      botAccountRef,
      senderRef,
    });
    const row = this.users.getById(this.ownerUserId);
    if (!row) {
      throw new UserAdmissionError("OWNER_ROW_MISSING");
    }
    return Object.freeze({
      route: "owner",
      userContext: buildUserContextFromRow(row, {
        channel: this.channel,
        botAccountRef,
      }),
      modelCalls: null,
    });
  }

  #inviteCandidate(text) {
    const trimmed = normalizeText(text);
    if (!trimmed || RESERVED_INPUTS.includes(trimmed)) {
      return null;
    }
    return INVITE_CANDIDATE.test(trimmed) ? trimmed : null;
  }

  #admitUnregistered({ botAccountRef, senderRef, text }) {
    const inviteCode = this.#inviteCandidate(text);
    let result;
    try {
      result = this.registration.start({
        botAccountRef,
        senderRef,
        channel: this.channel,
        inviteCode,
      });
    } catch {
      // An unknown, spent, expired or revoked code creates no row and spends no
      // tokens; the sender is simply asked for a valid code again.
      return reply(ACTIONS.REQUEST_INVITE);
    }
    return reply(result.action);
  }

  #admitPendingConsent({ botAccountRef, senderRef, text }) {
    const trimmed = normalizeText(text);
    if (trimmed === COMMANDS.CONSENT) {
      const result = this.registration.consent({
        botAccountRef,
        senderRef,
        channel: this.channel,
        accepted: true,
      });
      return reply(result.action);
    }
    if (trimmed === COMMANDS.DECLINE) {
      return reply(ACTIONS.CONSENT_DECLINED);
    }
    if (trimmed === COMMANDS.CANCEL) {
      return reply(ACTIONS.CANCELLED);
    }
    return reply(ACTIONS.SHOW_CONSENT);
  }

  // The single decision every inbound turn passes through. It returns exactly
  // one of three routes and never a partially-admitted turn:
  //
  //   owner  -> the pre-existing Owner runtime path, with a UserContext attached
  //   user   -> the ordinary-user model path (budget, circuit, provider router)
  //   reply  -> a frozen Chinese onboarding reply, modelCalls: 0
  admit({ botAccountRef, senderRef, text = "" }) {
    if (!normalizeText(botAccountRef) || !normalizeText(senderRef)) {
      throw new UserAdmissionError("PRINCIPAL_REQUIRED");
    }
    if (this.isOwnerSender(senderRef)) {
      return this.#admitOwner({ botAccountRef, senderRef });
    }

    const existing = this.users.resolveByPrincipal({
      channel: this.channel,
      botAccountRef,
      senderRef,
    });
    if (!existing) {
      return this.#admitUnregistered({ botAccountRef, senderRef, text });
    }
    if (existing.status === "suspended") {
      return reply(ACTIONS.SUSPENDED);
    }
    if (existing.status === "deleting" || existing.status === "deleted") {
      // A user in the deletion pipeline is not resurrected by sending a
      // message, and never reaches a provider.
      return reply(ACTIONS.SUSPENDED);
    }
    if (existing.status !== "active") {
      return this.#admitPendingConsent({ botAccountRef, senderRef, text });
    }

    let userContext;
    try {
      userContext = buildUserContextFromRow(existing, {
        channel: this.channel,
        botAccountRef,
      });
    } catch (error) {
      if (error instanceof UserContextError) {
        return reply(ACTIONS.SUSPENDED);
      }
      throw error;
    }
    // AC-004 / AC-041 restated at the anchor: the repository, not the message,
    // is what says a turn may spend tokens.
    if (!this.users.mayCallModel(userContext.userId)) {
      return reply(ACTIONS.SUSPENDED);
    }
    return Object.freeze({ route: "user", userContext, modelCalls: null });
  }

  // Owner-only surface for issuing the codes an ordinary user needs to register.
  issueInvite({ maxUses = 1, ttlMs = 7 * 24 * 60 * 60 * 1000 } = {}) {
    if (!this.invites) {
      throw new UserAdmissionError("REGISTRATION_MODE_IS_OPEN");
    }
    return this.invites.issue({ maxUses, ttlMs });
  }
}

module.exports = {
  INVITE_CANDIDATE,
  RESERVED_INPUTS,
  UserAdmissionError,
  UserAdmissionService,
  deriveSubKey,
};
