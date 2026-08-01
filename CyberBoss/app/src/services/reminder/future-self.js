"use strict";

// 提醒到点时把「当时那个人想干什么」交回去（CB9-410 / AC-017、FR-017）。
//
// FR-017 的原话：「提醒触发时恢复创建提醒时的意图、上下文摘要、Session 和目标
// 用户，而不是只发送固定字符串。」
//
// 提醒是这个系统里唯一**跨时间**的东西。建的时候那个人在说一件事，到点的时候
// 那个上下文已经没了：他可能删了消息、换了话题、甚至换了个微信号。所以三样东
// 西必须在**创建时**就钉死，不能在触发时重新推导：
//
//   userScope  —— 重新推导要么推不出来（原消息删了），要么在多号场景下推给另
//                  一个人。AC-017 的「删除原消息不导致跨用户恢复」说的就是它。
//   sessionKey —— 唤醒的必须是他**那一个**会话。新开一个的话，模型不知道之前
//                  说过什么，「提醒你那件事」就变成了「提醒你某件事」。
//   intent     —— 他当时想干什么。没有它，到点时模型只能看到一句「到点了」。
//
// 另一条同样重要：**固定字符串路径不许冒充 Agent 唤醒**。「10 分钟后提醒我喝
// 水」到点就是原样发一句话，一次模型都不调。把它记成 agent 唤醒的话，排查时会
// 看到一次根本没发生过的模型调用，而那种假记录比没有记录更难查。

const { makeSessionEvent } = require("../timeline/session-event");

// 到点时这条提醒该怎么响。
//
//   direct  —— 固定字符串。原样发，零模型调用。
//   agent   —— 唤醒他那个会话，把意图摘要交回去。
//   orphan  —— 缺身份或缺会话，两者都做不了。
const WAKE_KINDS = Object.freeze(["direct", "agent", "orphan"]);

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

// 这条提醒到点时属于哪一类。
function wakeKindOf(reminder) {
  if (!reminder || typeof reminder !== "object") {
    return "orphan";
  }
  if (reminder.direct === true) {
    return "direct";
  }
  // agent 唤醒要求身份和会话**都在**。缺一个就不是唤醒，是一条孤儿记录——
  // 硬着头皮唤醒的话，要么用一个猜出来的身份，要么新开一个会话，两者都比
  // 「如实说它成了孤儿」糟糕。
  return normalizeText(reminder.userScope) && normalizeText(reminder.sessionKey)
    ? "agent"
    : "orphan";
}

// 到点时把创建时的东西取回来。
//
// **只从这条记录里取**，一个字段都不重新推导。这是 AC-017 那半条「删除原消息
// 不导致跨用户恢复」唯一可靠的实现方式：不去查原消息，就不可能查错人。
function restoreContext(reminder) {
  const kind = wakeKindOf(reminder);
  return Object.freeze({
    wake_kind: kind,
    user_scope: normalizeText(reminder?.userScope) || null,
    session_key: normalizeText(reminder?.sessionKey) || null,
    intent: normalizeText(reminder?.intent) || null,
    created_at: normalizeText(reminder?.createdAt) || null,
    // 到点要说的那句话。direct 那条路上它就是全部内容；agent 那条路上它是
    // 给模型的一个起点，不是最终输出。
    text: normalizeText(reminder?.text) || null,
  });
}

// 交给模型的那段话（只在 agent 那条路上用）。
//
// 把「当时」和「现在」分开写：模型需要知道这是一件**过去的**约定到期了，
// 而不是用户此刻说了这句话。混在一起的话它会当成新指令去执行。
function buildAgentWakePrompt(reminder, { nowLabel = "" } = {}) {
  const restored = restoreContext(reminder);
  if (restored.wake_kind !== "agent") {
    return "";
  }
  const lines = [
    "这是一条到期的提醒，不是用户刚发来的消息。",
    restored.created_at ? `他是在 ${restored.created_at} 让你记下的。` : "",
    restored.intent ? `当时他要的是：${restored.intent}` : "",
    restored.text ? `到点该说的那句：${restored.text}` : "",
    nowLabel ? `现在是 ${nowLabel}。` : "",
    "接着他当时那个话头说，不要当成一条新指令。",
  ];
  return lines.filter(Boolean).join("\n");
}

// 到点这一刻记一条事件（CB9-400 的统一模型）。
//
// wake_kind 进 intent 而不是进公开载荷：公开面看得到「这是一次 direct 还是
// agent」是有用的运维信息，而具体说了什么不该出去。
function buildFiredEvent(reminder, { mode = "COMPANION", at = new Date() } = {}) {
  const restored = restoreContext(reminder);
  if (restored.wake_kind === "orphan") {
    // 孤儿记录也要有事件：它是一次**没能发生**的唤醒，而排查时最想知道的
    // 恰恰是「为什么那条提醒没响」。
    return makeSessionEvent({
      type: "reminder_fired",
      mode: "SYSTEM",
      // 没有身份就用记录 id 兜住 scope——它不是一个人，但它让这条事件仍然
      // 可以被检索到。
      userScope: `orphan_${normalizeText(reminder?.id) || "unknown"}`,
      sessionKey: `orphan_${normalizeText(reminder?.id) || "unknown"}`,
      idempotencyKey: `reminder-fired ${normalizeText(reminder?.id)}`,
      intent: "orphan_reminder",
      status: "failed",
      publicPayload: { wake_kind: "orphan", reason: "missing_scope_or_session" },
      at,
    });
  }
  return makeSessionEvent({
    type: "reminder_fired",
    mode: restored.wake_kind === "direct" ? "SYSTEM" : mode,
    userScope: restored.user_scope || `direct_${normalizeText(reminder?.senderId)}`,
    sessionKey: restored.session_key || `direct_${normalizeText(reminder?.id)}`,
    // 同一条提醒只响一次。重放拿到同一个 event_id，下游据此认出重复。
    idempotencyKey: `reminder-fired ${normalizeText(reminder?.id)}`,
    intent: restored.wake_kind === "agent" ? "agent_wake" : "fixed_string",
    status: "succeeded",
    publicPayload: {
      wake_kind: restored.wake_kind,
      // 有没有带上意图摘要——这是 FR-017 那句「不是只发送固定字符串」在
      // 运维面唯一看得见的证据。
      has_intent: Boolean(restored.intent),
    },
    at,
  });
}

module.exports = {
  WAKE_KINDS,
  buildAgentWakePrompt,
  buildFiredEvent,
  restoreContext,
  wakeKindOf,
};
