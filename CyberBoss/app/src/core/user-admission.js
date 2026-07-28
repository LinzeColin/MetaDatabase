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

const { buildSecureSetupLink } = require("../services/security/secure-setup-link");
const { SqliteSetupTokenService } = require("../services/security/setup-token-service");
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
const SETUP_COMMAND = "设置";
// 主人专用的两个中文口令。普通用户说这两个词只会拿到帮助，不会拿到邀请码，
// 也不会看到运行状况。
const OWNER_COMMANDS = Object.freeze({
  INVITE: ["邀请", "邀请码", "生成邀请码", "加个人"],
  STATUS: ["状态", "运行状况", "还好吗"],
});
const HELP_COMMANDS = Object.freeze(["帮助", "help", "怎么用", "你能做什么"]);
const RESERVED_INPUTS = Object.freeze([
  ...Object.values(COMMANDS),
  SETUP_COMMAND,
  ...OWNER_COMMANDS.INVITE,
  ...OWNER_COMMANDS.STATUS,
  ...HELP_COMMANDS,
]);
const INVITE_CANDIDATE = /^[A-Za-z0-9-]{8,64}$/;

const OWNER_HELP = [
  "你是这里的主人。可以直接跟我说话，也可以用这些中文口令：",
  "",
  "  邀请  —— 生成一串邀请码，转发给朋友，他就能开通",
  "  状态  —— 看看现在运行得怎么样",
  "  帮助  —— 再看一次这条说明",
].join("\n");

const USER_HELP = [
  "可以直接跟我说话。也可以用这些中文口令：",
  "",
  "  设置  —— 打开设置页面，填你自己的 AI 密钥",
  "  帮助  —— 再看一次这条说明",
  "  导出我的数据 / 删除我的数据  —— 你的数据你说了算",
].join("\n");

const INVITE_REPLY = (code) => [
  "邀请码给你：",
  "",
  code,
  "",
  "把上面这一串转发给朋友，让他加我之后直接发过来就行。",
  "这串码只能用一次，7 天内有效。",
].join("\n");

const SETUP_MESSAGES = Object.freeze({
  // The link carries the token in the URL fragment, so it never reaches a
  // server log or a proxy access log. It is single-use and short-lived.
  ISSUED: (link) =>
    `这是你的设置页面链接，15 分钟内有效，只能打开一次：\n${link}`,
  NOT_CONFIGURED:
    "设置页面还没有对外地址，暂时打不开。请让管理员配置 CB_PORTAL_ORIGIN 之后再试。",
  FAILED: "设置链接暂时生成不了，稍后再试一次。",
});

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
    portalOrigin = "",
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
    this.portalOrigin = normalizeText(portalOrigin);
    this.setupTokens = new SqliteSetupTokenService({ database });
  }

  // CB-620 / AC-011 on the live path: 「设置」 mints a single-use, 15-minute
  // token and puts it in the URL fragment, so the token never reaches a server
  // or proxy access log. With no portal origin configured the user is told
  // plainly rather than handed a link that cannot work.
  #issueSetupLink(userContext) {
    if (!this.portalOrigin) {
      return reply(ACTIONS.SHOW_HOME, { text: SETUP_MESSAGES.NOT_CONFIGURED });
    }
    try {
      const issued = this.setupTokens.issue({
        userId: userContext.userId,
        purpose: "provider",
      });
      return reply(ACTIONS.SHOW_HOME, {
        text: SETUP_MESSAGES.ISSUED(
          buildSecureSetupLink({
            origin: this.portalOrigin,
            token: issued.token,
            purpose: issued.purpose,
          }),
        ),
      });
    } catch {
      return reply(ACTIONS.SHOW_HOME, { text: SETUP_MESSAGES.FAILED });
    }
  }

  isOwnerSender(senderRef) {
    return this.ownerSenderIds.includes(normalizeText(senderRef));
  }

  // Nobody should have to look up their own WeChat id to install this. On a
  // fresh install with no Owner named and no Owner principal bound yet, the
  // first sender to say anything claims the Owner role — the person who just
  // scanned the login QR code is the only one who can be first.
  //
  // The window closes the instant it is used: `bindOwnerChannel` writes the
  // binding, `#ownerPrincipalBound` then sees it, and every later sender goes
  // through invite and consent like anyone else. It never reopens, because the
  // binding is durable and this checks the database rather than a flag.
  #ownerClaimAvailable() {
    if (this.ownerSenderIds.length > 0) {
      return false;
    }
    return !this.#ownerPrincipalBound();
  }

  #ownerPrincipalBound() {
    const row = this.users.database
      .prepare(
        `SELECT EXISTS(
           SELECT 1 FROM user_channels
           WHERE user_id=? AND revoked_at IS NULL
         ) AS bound`,
      )
      .get(this.ownerUserId);
    return Number(row.bound) === 1;
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

  // The Owner's turn, with the two Owner-only Chinese words handled before the
  // message ever reaches a runtime. Anything else is an ordinary Owner turn and
  // continues down the pre-existing path untouched.
  #ownerTurn({ botAccountRef, senderRef, text }) {
    const admitted = this.#admitOwner({ botAccountRef, senderRef });
    const trimmed = normalizeText(text);
    if (OWNER_COMMANDS.INVITE.includes(trimmed)) {
      return this.#issueInviteReply();
    }
    if (OWNER_COMMANDS.STATUS.includes(trimmed)) {
      return Object.freeze({ route: "status", userContext: admitted.userContext, modelCalls: 0 });
    }
    if (HELP_COMMANDS.includes(trimmed)) {
      return reply(ACTIONS.SHOW_HOME, { text: OWNER_HELP });
    }
    return admitted;
  }

  #issueInviteReply() {
    if (!this.invites) {
      return reply(ACTIONS.SHOW_HOME, {
        text: "现在是开放模式，任何人加我之后直接说话就能用，不需要邀请码。",
      });
    }
    try {
      const invite = this.invites.issue({ maxUses: 1, ttlMs: 7 * 24 * 60 * 60 * 1000 });
      return reply(ACTIONS.SHOW_HOME, { text: INVITE_REPLY(invite.code) });
    } catch {
      return reply(ACTIONS.SHOW_HOME, { text: "邀请码这会儿生成不出来，稍后再发一次「邀请」。" });
    }
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
      return this.#ownerTurn({ botAccountRef, senderRef, text });
    }
    if (this.#ownerClaimAvailable()) {
      const claimed = this.#admitOwner({ botAccountRef, senderRef });
      return Object.freeze({ ...claimed, ownerClaimed: true });
    }

    const existing = this.users.resolveByPrincipal({
      channel: this.channel,
      botAccountRef,
      senderRef,
    });
    if (!existing) {
      return this.#admitUnregistered({ botAccountRef, senderRef, text });
    }
    // The stored role is the authority, not the configured sender list. Without
    // this, an Owner who claimed the role on first contact would be resolved
    // here as an ordinary user on every later message and routed to the BYOK
    // provider path instead of their own runtime.
    if (existing.role === "owner") {
      return this.#ownerTurn({ botAccountRef, senderRef, text });
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
    const trimmed = normalizeText(text);
    if (trimmed === SETUP_COMMAND) {
      return this.#issueSetupLink(userContext);
    }
    if (HELP_COMMANDS.includes(trimmed)) {
      return reply(ACTIONS.SHOW_HOME, { text: USER_HELP });
    }
    // An ordinary user asking for an Owner word gets the ordinary help, never a
    // hint that a privileged command exists.
    if (
      OWNER_COMMANDS.INVITE.includes(trimmed)
      || OWNER_COMMANDS.STATUS.includes(trimmed)
    ) {
      return reply(ACTIONS.SHOW_HOME, { text: USER_HELP });
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
  HELP_COMMANDS,
  INVITE_CANDIDATE,
  OWNER_COMMANDS,
  OWNER_HELP,
  RESERVED_INPUTS,
  SETUP_COMMAND,
  SETUP_MESSAGES,
  USER_HELP,
  UserAdmissionError,
  UserAdmissionService,
  deriveSubKey,
};
