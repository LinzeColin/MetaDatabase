class SystemMessageDispatcher {
  constructor({ queueStore, config, accountId }) {
    this.queueStore = queueStore;
    this.config = config;
    this.accountId = accountId;
  }

  // 所有号的，不只是主号。this.accountId 只在消息自己没带号时兜底。
  //
  // 这个 dispatcher 是按**一个**号构造的（start() 里传的是 resolveAccount() 的主
  // 号），但机器上有三个号，轮询器按每个人自己的号排队。按主号取的话，另外两个号
  // 的消息进队就再也出不来，而且 hasPendingForAccount 会让轮询器从此跳过那个号。
  hasPending() {
    return typeof this.queueStore.hasPending === "function"
      ? this.queueStore.hasPending()
      : this.queueStore.hasPendingForAccount(this.accountId);
  }

  drainPending() {
    return typeof this.queueStore.drainAll === "function"
      ? this.queueStore.drainAll()
      : this.queueStore.drainForAccount(this.accountId);
  }

  requeue(message) {
    return this.queueStore.enqueue(message);
  }

  resolveWorkspaceRoot(message) {
    return normalizeText(message?.workspaceRoot) || normalizeText(this.config.workspaceRoot);
  }

  buildPreparedMessage(message, contextToken = "") {
    return {
      provider: "system",
      workspaceId: this.config.workspaceId,
      // 这条消息自己是哪个号的就用哪个号。写死 this.accountId 的话，取出来也会
      // 投到主号上——那个人根本不在主号下面，消息发不到他手上。
      accountId: normalizeText(message?.accountId) || this.accountId,
      chatId: message.senderId,
      threadKey: `system:${message.senderId}`,
      senderId: message.senderId,
      messageId: message.id,
      text: buildSystemInboundText(message?.text, message?.createdAt),
      attachments: [],
      command: "message",
      contextToken,
      receivedAt: normalizeIsoTime(message?.createdAt) || new Date().toISOString(),
      workspaceRoot: this.resolveWorkspaceRoot(message),
    };
  }
}

function buildSystemInboundText(text, createdAt = "") {
  const body = normalizeText(text);
  const localTime = formatSystemLocalTime(createdAt);
  const sections = [
    // 时区跟入站那条保持一致，理由见 inbound-turn.js 的同名注释。
    ...(localTime ? [`[${localTime} 北京时间]`, ""] : []),
    "SYSTEM ACTION MODE: internal trigger, not user chat.",
    "Do any timeline/diary/reminder/whereabouts work in this turn.",
    "If you act, end with send_message that briefly and naturally reflects what you did or what changed; use silent only if you do nothing.",
    "Return exactly one JSON object after any tool calls:",
    "{\"action\":\"silent\"}",
    "{\"action\":\"send_message\",\"message\":\"<one short natural WeChat message>\"}",
    "No markdown fences. No reasoning. No text outside the JSON.",
  ];
  if (body) {
    sections.push("", "Trigger:", body);
  }
  return sections.join("\n").trim();
}

function formatSystemLocalTime(value) {
  const normalized = normalizeIsoTime(value);
  if (!normalized) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(normalized)).replace(/\//g, "-");
}

function normalizeIsoTime(value) {
  const normalized = normalizeText(value);
  if (!normalized) {
    return "";
  }
  const parsed = Date.parse(normalized);
  if (!Number.isFinite(parsed)) {
    return "";
  }
  return new Date(parsed).toISOString();
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

module.exports = { SystemMessageDispatcher };
