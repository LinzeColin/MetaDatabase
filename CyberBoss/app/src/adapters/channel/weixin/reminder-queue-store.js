const fs = require("fs");
const path = require("path");

class ReminderQueueStore {
  constructor({ filePath }) {
    this.filePath = filePath;
    this.state = { reminders: [] };
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
      const reminders = Array.isArray(parsed?.reminders) ? parsed.reminders : [];
      this.state = {
        reminders: reminders
          .map(normalizeReminder)
          .filter(Boolean)
          .sort((left, right) => left.dueAtMs - right.dueAtMs),
      };
    } catch {
      this.state = { reminders: [] };
    }
  }

  save() {
    fs.writeFileSync(this.filePath, JSON.stringify(this.state, null, 2));
  }

  enqueue(reminder) {
    this.load();
    const normalized = normalizeReminder(reminder);
    if (!normalized) {
      throw new Error("invalid reminder");
    }
    this.state.reminders.push(normalized);
    this.state.reminders.sort((left, right) => left.dueAtMs - right.dueAtMs);
    this.save();
    return normalized;
  }

  listDue(nowMs = Date.now()) {
    this.load();
    const due = [];
    const pending = [];

    for (const reminder of this.state.reminders) {
      if (reminder.dueAtMs <= nowMs) {
        due.push(reminder);
      } else {
        pending.push(reminder);
      }
    }

    if (due.length) {
      this.state.reminders = pending;
      this.save();
    }

    return due;
  }

  peekNextDueAtMs() {
    this.load();
    const first = this.state.reminders[0];
    return Number.isFinite(first?.dueAtMs) ? first.dueAtMs : 0;
  }
}

function normalizeReminder(reminder) {
  if (!reminder || typeof reminder !== "object") {
    return null;
  }
  const id = typeof reminder.id === "string" ? reminder.id.trim() : "";
  const accountId = typeof reminder.accountId === "string" ? reminder.accountId.trim() : "";
  const senderId = typeof reminder.senderId === "string" ? reminder.senderId.trim() : "";
  const contextToken = typeof reminder.contextToken === "string" ? reminder.contextToken.trim() : "";
  const text = typeof reminder.text === "string" ? reminder.text.trim() : "";
  const dueAtMs = Number(reminder.dueAtMs);
  const createdAt = typeof reminder.createdAt === "string" ? reminder.createdAt.trim() : "";
  if (!id || !accountId || !senderId || !contextToken || !text || !Number.isFinite(dueAtMs) || dueAtMs <= 0) {
    return null;
  }
  // Future-self 三件套（CB9-410 / AC-017）。
  //
  // 提醒是**跨时间**的：建的时候那个人在说一件事，到点的时候那个上下文已经没
  // 了。只存一句 text 的话，到点能做的就只有把那句话原样吐出来——AC-017 明说
  // 「不是只发送固定字符串」。
  //
  // 三样都在创建时就定死，**不在触发时重新推导**：
  //   userScope  —— 到点时那条原始消息可能已经被删了。重新推导要么推不出来，
  //                  要么在多号场景下推给另一个人。这是 AC-017 里
  //                  「删除原消息不导致跨用户恢复」那半条。
  //   sessionKey —— 唤醒的必须是他**那一个**会话，不是新开一个。
  //   intent     —— 他当时想干什么。到点时把这句摘要交回给模型，它才知道
  //                  「叫你一声」是为了什么。
  const userScope = typeof reminder.userScope === "string" ? reminder.userScope.trim() : "";
  const sessionKey = typeof reminder.sessionKey === "string" ? reminder.sessionKey.trim() : "";
  const intent = typeof reminder.intent === "string" ? reminder.intent.trim().slice(0, 200) : "";
  return {
    id,
    accountId,
    senderId,
    contextToken,
    text,
    dueAtMs,
    // 空串而不是 undefined：JSON 里 undefined 会整个字段消失，而消失的字段和
    // 「这个人没有会话」在读回来的时候长得一模一样。
    userScope,
    sessionKey,
    intent,
    createdAt: createdAt || new Date().toISOString(),
    // direct=true 的是「X 分钟后提醒我」当场解析出来的那种：到点原样发出去，
    // **不唤醒模型**。模型那条路（cyberboss_reminder_create）留给需要它临场
    // 判断该说什么的场景，两者到期后走的出口不一样。
    //
    // AC-017 的第三条：「固定字符串路径不冒充 Agent 唤醒」。所以这一位不只是
    // 一个内部开关，它决定到点时记的是哪一类事件——把 direct 记成 agent 唤醒，
    // 排查时会看到一次根本没发生过的模型调用。
    direct: reminder.direct === true,
    // 投递失败重排了几次。丢了这个字段，重排就会变成无限重试。
    attempts: Number.isSafeInteger(reminder.attempts) && reminder.attempts >= 0
      ? reminder.attempts
      : 0,
  };
}

module.exports = { ReminderQueueStore };
