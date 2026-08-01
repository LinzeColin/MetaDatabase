const fs = require("fs");
const path = require("path");

class SystemMessageQueueStore {
  constructor({ filePath }) {
    this.filePath = filePath;
    this.state = { messages: [] };
    this.ensureParentDirectory();
    this.load();
  }

  ensureParentDirectory() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
  }

  load() {
    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      const parsed = JSON.parse(raw);
      const messages = Array.isArray(parsed?.messages) ? parsed.messages : [];
      this.state = {
        messages: messages
          .map(normalizeSystemMessage)
          .filter(Boolean)
          .sort(compareSystemMessages),
      };
    } catch {
      this.state = { messages: [] };
    }
  }

  save() {
    fs.writeFileSync(this.filePath, JSON.stringify(this.state, null, 2));
  }

  enqueue(message) {
    this.load();
    const normalized = normalizeSystemMessage(message);
    if (!normalized) {
      throw new Error("invalid system message");
    }
    this.state.messages.push(normalized);
    this.state.messages.sort(compareSystemMessages);
    this.save();
    return normalized;
  }

  drainForAccount(accountId) {
    this.load();
    const normalizedAccountId = normalizeText(accountId);
    const drained = [];
    const pending = [];

    for (const message of this.state.messages) {
      if (message.accountId === normalizedAccountId) {
        drained.push(message);
      } else {
        pending.push(message);
      }
    }

    if (drained.length) {
      this.state.messages = pending;
      this.save();
    }

    return drained;
  }

  hasPendingForAccount(accountId) {
    this.load();
    const normalizedAccountId = normalizeText(accountId);
    return this.state.messages.some((message) => message.accountId === normalizedAccountId);
  }

  // 所有号的，一次全取走。
  //
  // 只按主号排空是「boss 只主动找我」的真正原因：轮询器按**每个人自己的号**排队，
  // 而取的那一侧钉死了主号。于是别的号下面的人，消息进了队就再也没人取；更糟的是
  // hasPendingForAccount 从此对那个号永远为真，轮询器每一轮都跳过他——一条卡住
  // 之后那个号就彻底哑了。线上卡了两条，一条从 2026-07-29 10:40 起躺了一整天。
  drainAll() {
    this.load();
    const drained = this.state.messages.slice();
    if (drained.length) {
      this.state.messages = [];
      this.save();
    }
    return drained;
  }

  hasPending() {
    this.load();
    return this.state.messages.length > 0;
  }
}

function normalizeSystemMessage(message) {
  if (!message || typeof message !== "object") {
    return null;
  }

  const id = normalizeText(message.id);
  const accountId = normalizeText(message.accountId);
  const senderId = normalizeText(message.senderId);
  const workspaceRoot = normalizeText(message.workspaceRoot);
  const text = normalizeText(message.text);
  const createdAt = normalizeIsoTime(message.createdAt);

  if (!id || !accountId || !senderId || !workspaceRoot || !text) {
    return null;
  }

  return {
    id,
    accountId,
    senderId,
    workspaceRoot,
    text,
    createdAt: createdAt || new Date().toISOString(),
    // 投递失败重排的次数。没有上限的话，一条永远投不出去的消息会把它那个号
    // 永远堵住（hasPendingForAccount 一直为真 → 轮询器每一轮都跳过那个号下面
    // 的人），整个号从此静默，而且没有任何东西会报错。这正是这次「boss 只找
    // 主人」的形状，只是原因换了一个。
    attempts: Number.isInteger(message.attempts) && message.attempts > 0 ? message.attempts : 0,
    // 会话身份（CB9-420 / AC-018）。
    //
    // 不落盘的话，进程一重启这条排着的问候就丢了归属——发出去的时候会新开一个
    // 会话，模型不知道之前说过什么，「主动关心」变成「陌生人搭讪」。
    // 空串而不是 undefined：JSON 里 undefined 让字段整个消失，而消失的字段和
    // 「这个人没有会话」读回来长得一模一样。
    userScope: normalizeText(message.userScope),
    sessionKey: normalizeText(message.sessionKey),
    // 主人的脉冲和访客的主动关心是两件事。混在一起的话，「boss 是不是只找主人」
    // 这个问题又要靠翻队列文件来答。
    pulseKind: ["owner_pulse", "companion_checkin"].includes(message.pulseKind)
      ? message.pulseKind
      : "",
  };
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

function compareSystemMessages(left, right) {
  const leftTime = Date.parse(left?.createdAt || "") || 0;
  const rightTime = Date.parse(right?.createdAt || "") || 0;
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  return String(left?.id || "").localeCompare(String(right?.id || ""));
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

module.exports = { SystemMessageQueueStore };
