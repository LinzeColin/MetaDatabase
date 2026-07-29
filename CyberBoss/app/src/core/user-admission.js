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

const { createHmac, timingSafeEqual } = require("node:crypto");

const { buildSecureSetupLink } = require("../services/security/secure-setup-link");
const { SqliteSetupTokenService } = require("../services/security/setup-token-service");
const {
  SqliteInviteCodeStore,
  generateCode,
  normalizeCode,
} = require("../services/users/invite-code-store");
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
  // 「我不可能每次都有 token」。主人手上永远有的东西是微信本身，所以后台入口
  // 就在这里：说一声，拿一条一次性链接。长期令牌一次都不经过聊天记录。
  ADMIN: ["后台", "面板", "网站", "控制台", "管理后台"],
});
const HELP_COMMANDS = Object.freeze(["帮助", "help", "怎么用", "你能做什么"]);
// 主人认领码。存在 service_state 里：明文永不落库，只留 HMAC 摘要和过期时间。
const OWNER_CLAIM_STATE_KEY = "owner_claim";
const OWNER_CLAIM_TTL_MS = 30 * 60 * 1000;
// 「开一扇门」：一段有限的时间窗，窗内第一个说话的人成为主人。比让人抄一串码
// 好用，也比"永远开着的先到先得"安全——窗是主人自己开的，而且很快自己关上。
const OWNER_BIND_WINDOW_KEY = "owner_bind_window";
const OWNER_BIND_WINDOW_TTL_MS = 10 * 60 * 1000;
const RESERVED_INPUTS = Object.freeze([
  ...Object.values(COMMANDS),
  SETUP_COMMAND,
  ...OWNER_COMMANDS.INVITE,
  ...OWNER_COMMANDS.STATUS,
  ...OWNER_COMMANDS.ADMIN,
  ...HELP_COMMANDS,
]);
const INVITE_CANDIDATE = /^[A-Za-z0-9-]{8,64}$/;

const OWNER_HELP = [
  "你是这里的主人。可以直接跟我说话，也可以用这些中文口令：",
  "",
  "  后台  —— 给你一条打开后台的链接（一次性，5 分钟有效）",
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
    // 普通用户席位上限。开放模式下这是唯一挡住"任何扫到码的人都来烧主人额度"
    // 的东西，所以它必须在**建用户之前**判，而不是等 turn 走到模型那一步。
    // 回调而不是定值：主人在后台改完，下一条消息就生效，不用重启。
    seatLimitProvider = null,
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
    this.seatLimitProvider = typeof seatLimitProvider === "function" ? seatLimitProvider : null;
    this.setupTokens = new SqliteSetupTokenService({ database });
    this.now = now;
    // 和邀请码同样的做法：从 owner-only 的身份密钥派生，不新增任何密钥文件。
    this.ownerClaimSecret = deriveSubKey(identityKey, "cyberboss-owner-claim-secret");
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
  #hashOwnerClaim(code) {
    return createHmac("sha256", this.ownerClaimSecret)
      .update("cyberboss-owner-claim")
      .update(normalizeCode(code))
      .digest("hex");
  }

  // 后台生成的一次性认领码。授权来自后台令牌——那是只有服务器管理者才拿得到
  // 的东西——所以这条路径不会把主人身份交给一个陌生人。
  //
  // 它补的是一个真实的死局：主人用自己的微信当了机器人号，那个号的 id 永远
  // 不会作为"发件人"出现，于是主人永远绑不上；而 ownerSenderIds 一旦有值，
  // 先到先得的认领窗口又是关着的。结果是谁都成不了主人，机器人对每个人都回
  // 一句"这个操作只有管理员可以使用"。
  issueOwnerClaim({ ttlMs = OWNER_CLAIM_TTL_MS } = {}) {
    const code = generateCode();
    const expiresAt = this.now().getTime() + ttlMs;
    this.users.database
      .prepare(
        `INSERT INTO service_state (key, value_redacted_json, value_sha256, updated_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(key) DO UPDATE SET
           value_redacted_json=excluded.value_redacted_json,
           value_sha256=excluded.value_sha256,
           updated_at=excluded.updated_at`,
      )
      .run(
        OWNER_CLAIM_STATE_KEY,
        JSON.stringify({ expires_at: expiresAt }),
        this.#hashOwnerClaim(code),
        this.now().toISOString(),
      );
    return Object.freeze({ code, expiresAt: new Date(expiresAt).toISOString() });
  }

  // 一次性：只要摘要对得上就删掉，不管过没过期。过期的码返回 false，但也不会
  // 留在库里等人再试一次。
  #redeemOwnerClaim(text) {
    const candidate = normalizeCode(text);
    if (candidate.length < 12) {
      return false;
    }
    const row = this.users.database
      .prepare("SELECT value_redacted_json, value_sha256 FROM service_state WHERE key=?")
      .get(OWNER_CLAIM_STATE_KEY);
    if (!row) {
      return false;
    }
    let digest;
    try {
      digest = this.#hashOwnerClaim(candidate);
    } catch {
      return false;
    }
    const stored = Buffer.from(String(row.value_sha256 || ""), "utf8");
    const actual = Buffer.from(digest, "utf8");
    if (stored.length !== actual.length || !timingSafeEqual(stored, actual)) {
      return false;
    }
    this.users.database
      .prepare("DELETE FROM service_state WHERE key=?")
      .run(OWNER_CLAIM_STATE_KEY);
    let expiresAt = 0;
    try {
      expiresAt = Number(JSON.parse(row.value_redacted_json)?.expires_at) || 0;
    } catch {
      return false;
    }
    return expiresAt > this.now().getTime();
  }

  // 有没有任何微信号已经绑成主人。没有的话，这套系统里还不存在任何用户数据，
  // 后台也就没有什么可保护的——首次绑定因此不需要令牌。
  ownerChannelBound() {
    return this.#ownerPrincipalBound();
  }

  armOwnerBinding({ ttlMs = OWNER_BIND_WINDOW_TTL_MS } = {}) {
    if (this.#ownerPrincipalBound()) {
      throw new UserAdmissionError("OWNER_ALREADY_BOUND");
    }
    const expiresAt = this.now().getTime() + ttlMs;
    this.users.database
      .prepare(
        `INSERT INTO service_state (key, value_redacted_json, value_sha256, updated_at)
         VALUES (?, ?, '', ?)
         ON CONFLICT(key) DO UPDATE SET
           value_redacted_json=excluded.value_redacted_json,
           updated_at=excluded.updated_at`,
      )
      .run(OWNER_BIND_WINDOW_KEY, JSON.stringify({ expires_at: expiresAt }), this.now().toISOString());
    return Object.freeze({ expiresAt: new Date(expiresAt).toISOString(), ttlMs });
  }

  // 窗开着、还没过期、而且确实还没有主人——三件事都成立才放行。用完即关。
  #ownerBindingArmed() {
    if (this.#ownerPrincipalBound()) {
      return false;
    }
    const row = this.users.database
      .prepare("SELECT value_redacted_json FROM service_state WHERE key=?")
      .get(OWNER_BIND_WINDOW_KEY);
    if (!row) {
      return false;
    }
    let expiresAt = 0;
    try {
      expiresAt = Number(JSON.parse(row.value_redacted_json)?.expires_at) || 0;
    } catch {
      expiresAt = 0;
    }
    if (expiresAt <= this.now().getTime()) {
      this.users.database.prepare("DELETE FROM service_state WHERE key=?").run(OWNER_BIND_WINDOW_KEY);
      return false;
    }
    return true;
  }

  #closeOwnerBindingWindow() {
    this.users.database.prepare("DELETE FROM service_state WHERE key=?").run(OWNER_BIND_WINDOW_KEY);
  }

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
    if (OWNER_COMMANDS.ADMIN.includes(trimmed)) {
      // 链接由 app 层生成——票据服务在那边。这里只负责把这一轮判成"当场答复"，
      // 于是它一次模型调用都不花。
      return Object.freeze({ route: "admin_link", userContext: admitted.userContext, modelCalls: 0 });
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

  // 现在还剩几个席位。读不出来时返回 null＝不设限——席位判定坏掉不该把所有
  // 新用户都挡在门外，那会让"开放模式"变成"谁都进不来"。
  #seatsRemaining() {
    if (!this.seatLimitProvider) {
      return null;
    }
    let limit;
    try {
      limit = Number(this.seatLimitProvider());
    } catch {
      return null;
    }
    if (!Number.isInteger(limit) || limit < 0) {
      return null;
    }
    try {
      // 只数普通用户；主人不占席位。
      const active = this.users.countActiveOrdinaryUsers
        ? Number(this.users.countActiveOrdinaryUsers())
        : null;
      return Number.isFinite(active) ? Math.max(0, limit - active) : null;
    } catch {
      return null;
    }
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
    // 认领码要排在注册用户查表之前：主人换手机、换微信之后重新认领，走的也是
    // 这条路，而那时候他在库里可能已经是一个普通用户了。
    if (this.#redeemOwnerClaim(text)) {
      const claimed = this.#admitOwner({ botAccountRef, senderRef });
      return Object.freeze({ ...claimed, ownerClaimed: true });
    }
    // 主人在后台开了门：窗内第一句话，不管说的是什么，都把这个号绑成主人。
    if (this.#ownerBindingArmed()) {
      const claimed = this.#admitOwner({ botAccountRef, senderRef });
      this.#closeOwnerBindingWindow();
      return Object.freeze({ ...claimed, ownerClaimed: true });
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
      || OWNER_COMMANDS.ADMIN.includes(trimmed)
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
  OWNER_BIND_WINDOW_TTL_MS,
  OWNER_CLAIM_TTL_MS,
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
