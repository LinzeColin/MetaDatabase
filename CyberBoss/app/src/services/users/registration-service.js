"use strict";

// CB-620 / AC-004, AC-028, AC-041: invite-only registration bound to the
// WeChat principal. An unknown sender only ever reaches the minimal pending
// state; consent is what activates. Because identity is derived from the bot
// account plus the sender, the same WeChat account continues the same user
// from any client — no second account system exists.

const { ACTIONS, MESSAGES } = require("./onboarding-state");

const REGISTRATION_MODES = Object.freeze(["invite", "open"]);
const DEFAULT_POLICY_VERSION = "privacy-v1";
// The action a given stored state maps to, and whether that turn is allowed to
// consume model tokens. Only "active" is ever non-zero.
const STATE_OUTCOME = Object.freeze({
  unseen: Object.freeze({ action: ACTIONS.REQUEST_INVITE, modelCalls: 0 }),
  pending_invite: Object.freeze({ action: ACTIONS.REQUEST_INVITE, modelCalls: 0 }),
  pending_consent: Object.freeze({ action: ACTIONS.SHOW_CONSENT, modelCalls: 0 }),
  suspended: Object.freeze({ action: ACTIONS.SUSPENDED, modelCalls: 0 }),
  active: Object.freeze({ action: ACTIONS.SHOW_HOME, modelCalls: null }),
});

class RegistrationError extends Error {
  constructor(code) {
    super(code);
    this.name = "RegistrationError";
    this.code = code;
  }
}

class RegistrationService {
  constructor({
    userRepository,
    inviteStore = null,
    registrationMode = "invite",
    policyVersion = DEFAULT_POLICY_VERSION,
  }) {
    if (!REGISTRATION_MODES.includes(registrationMode)) {
      throw new RegistrationError("REGISTRATION_MODE_INVALID");
    }
    if (registrationMode === "invite" && !inviteStore) {
      throw new RegistrationError("INVITE_STORE_REQUIRED");
    }
    if (!userRepository) {
      throw new RegistrationError("USER_REPOSITORY_REQUIRED");
    }
    this.users = userRepository;
    this.invites = inviteStore;
    this.mode = registrationMode;
    this.policyVersion = policyVersion;
  }

  #stateOf(user) {
    if (!user) {
      return "unseen";
    }
    if (user.status === "suspended") {
      return "suspended";
    }
    return user.status === "active" ? "active" : "pending_consent";
  }

  // "开始" never activates anything: at most it creates a pending row.
  start({ botAccountRef, senderRef, channel = "weixin", inviteCode = null }) {
    const existing = this.users.resolveByPrincipal({
      channel,
      botAccountRef,
      senderRef,
    });
    if (existing) {
      // AC-028: an existing WeChat account resumes its own state from any
      // client; no new user row and no second identity are created.
      return this.#result(existing, this.#stateOf(existing), {
        resumed: true,
        createdUser: false,
      });
    }

    if (this.mode === "invite") {
      if (!inviteCode) {
        return this.#result(null, "pending_invite", {
          resumed: false,
          createdUser: false,
        });
      }
      // Throws INVITE_INVALID for unknown, spent, expired or revoked codes;
      // no user row is created in that case.
      this.invites.consume(inviteCode);
    }

    const user = this.users.ensurePending({
      channel,
      botAccountRef,
      senderRef,
    });
    return this.#result(user, "pending_consent", {
      resumed: false,
      createdUser: true,
    });
  }

  // "同意并开始" is the only transition that can produce an active user.
  consent({ botAccountRef, senderRef, channel = "weixin", accepted }) {
    const user = this.users.resolveByPrincipal({
      channel,
      botAccountRef,
      senderRef,
    });
    if (!user) {
      throw new RegistrationError("START_REQUIRED");
    }
    if (user.status === "suspended") {
      return this.#result(user, "suspended", { resumed: true, createdUser: false });
    }
    if (!accepted) {
      return Object.freeze({
        user: Object.freeze({ ...user }),
        state: "pending_consent",
        action: ACTIONS.CONSENT_DECLINED,
        message: MESSAGES[ACTIONS.CONSENT_DECLINED],
        modelCalls: 0,
        resumed: false,
        createdUser: false,
      });
    }
    const active =
      user.status === "active"
        ? this.users.getById(user.user_id)
        : this.users.activateConsent({
            userId: user.user_id,
            policyVersion: this.policyVersion,
          });
    return this.#result(active, "active", { resumed: false, createdUser: false });
  }

  suspend({ userId }) {
    return this.users.setStatus(userId, "suspended");
  }

  // The single authority every inbound turn consults before spending tokens.
  mayCallModel(userId) {
    return this.users.mayCallModel(userId);
  }

  #result(user, state, extra) {
    const outcome = STATE_OUTCOME[state];
    if (!outcome) {
      throw new RegistrationError("REGISTRATION_STATE_INVALID");
    }
    return Object.freeze({
      user: user ? Object.freeze({ ...user }) : null,
      state,
      action: outcome.action,
      message: MESSAGES[outcome.action],
      modelCalls: outcome.modelCalls,
      ...extra,
    });
  }
}

module.exports = {
  DEFAULT_POLICY_VERSION,
  REGISTRATION_MODES,
  RegistrationError,
  RegistrationService,
};
