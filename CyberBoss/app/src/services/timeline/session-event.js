"use strict";

// 统一事件模型（CB9-400 / AC-020、AC-043、FR-020）。
//
// FR-020 的原话：「消息、任务、提醒、脉冲、审批、工具、媒体、降级、投递和恢复
// 均写入统一事件模型。」十一类事件，一个形状。
//
// 为什么要统一：这些事件今天散在 Timeline、后台对话栏、运维日志和几个 JSON 文
// 件里，各写各的字段。「这个人昨天到底发生了什么」这个问题，今天要翻四个地方，
// 而且翻完还对不上——因为每个地方的时间口径和身份字段都不一样。
//
// **内部事件和公开投影是两个东西**，这是这个模块最重要的一条线：
//
//   内部事件 —— 带真实的 user_scope 和 session_key。它进库、进排查、进对账。
//   公开投影 —— 进公开页和 Status。AC-043 明说这里不许出现原始私聊、微信 ID、
//               真实 thread/session ID、绝对路径和 token。
//
// Starter Kit 的参考实现把 session_key 原样放进事件、由调用方决定公开哪些——
// 那等于把 AC-043 的责任交给了每一个调用点，而只要有一个忘了就是一次泄漏。
// 这里改成：投影是这个模块自己的函数，公开面只输出哈希，调用方**没有**「顺手
// 公开原值」这个选项。

const crypto = require("node:crypto");

const { canonicalStamp } = require("../time/canonical-time");

// 十一类。FR-020 逐字对应，不多不少——多一类意味着有东西绕过了统一模型，
// 少一类意味着那一类还散在别处。
const EVENT_TYPES = Object.freeze([
  "message",           // 消息
  "task",              // 任务
  "reminder_created",  // 提醒（建立）
  "reminder_fired",    // 提醒（触发）
  "pulse",             // 脉冲
  "approval",          // 审批
  "tool",              // 工具
  "media",             // 媒体
  "degraded",          // 降级
  "delivery",          // 投递
  "recovery",          // 恢复
]);

const MODES = Object.freeze(["OWNER", "COMPANION", "SYSTEM"]);

const STATUSES = Object.freeze([
  "accepted",   // 收下了
  "running",    // 在办
  "succeeded",  // 办成了
  "failed",     // 办砸了
  "skipped",    // 有意跳过（不是失败）
  "deferred",   // 存着等下次（微信 context_token 过期那条路）
]);

// 公开载荷里绝不允许出现的字段名。
//
// 按归一化后的名字比对：clientIp、client_ip、ClientIP 是同一个东西，而写这行
// 检查的人只会想到其中一种写法。
const FORBIDDEN_PUBLIC_KEYS = Object.freeze(new Set([
  "raw_message", "message_text", "text", "prompt", "response", "content", "body",
  "wechat_id", "wxid", "sender_id", "user_id", "account_id", "bot_account_id",
  "thread_id", "thread_ref", "session_id", "session_ref", "session_key",
  "workspace_ref", "workspace_root", "absolute_path", "path", "file_path",
  "token", "access_token", "refresh_token", "context_token", "secret", "api_key",
  "authorization", "credential", "password", "cookie", "set_cookie",
  "latitude", "longitude", "raw_ip", "ip", "address",
]));

// 值里的形状。字段名过了不等于值是干净的——一段原始私聊塞进一个叫 note 的
// 字段里，键名检查一点忙都帮不上。
const FORBIDDEN_PUBLIC_VALUE = /(wxid_[A-Za-z0-9_-]+|@im\.(?:bot|wechat)|\bBearer\s+[A-Za-z0-9._-]{20,}|\bsk-[A-Za-z0-9]{20,}|BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY|\/Users\/|\/home\/[^/\s]+\/|\/(?:root|opt|etc|var|tmp|srv|work)\/|[A-Za-z]:\\Users\\)/i;

const MAX_PUBLIC_PAYLOAD_BYTES = 16 * 1024;

function normalizeKey(key) {
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

// fail-closed：查到就抛，不是挑着放行。
// 悄悄丢弃会把上游的泄漏藏起来——那一版代码依然在往公开面塞原始私聊。
function assertPublicPayload(value, pointer = "$", seen = new WeakSet()) {
  if (value && typeof value === "object") {
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN_PUBLIC_KEYS.has(normalizeKey(key))) {
        throw new Error(`private field in public payload at ${pointer}.${key}`);
      }
      assertPublicPayload(child, `${pointer}.${key}`, seen);
    }
    return;
  }
  if (typeof value === "string" && FORBIDDEN_PUBLIC_VALUE.test(value)) {
    throw new Error(`private value in public payload at ${pointer}`);
  }
}

function deepFreeze(value, seen = new WeakSet()) {
  if (!value || typeof value !== "object" || seen.has(value)) {
    return value;
  }
  seen.add(value);
  for (const child of Object.values(value)) {
    deepFreeze(child, seen);
  }
  return Object.freeze(value);
}

function clone(value) {
  return typeof structuredClone === "function"
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}

// 同一件事只有一个 event_id。
//
// 由幂等键推出来而不是随机生成：崩溃后重放同一条消息必须得到同一个 id，
// 否则「重放不产生第二个副作用」就无从判断——两条一模一样但 id 不同的事件，
// 下游没有任何办法看出它们是同一件事。
function eventId({ idempotencyKey, type, sessionKey }) {
  return `evt_${crypto.createHash("sha256")
    // 分隔符用 \u0000 而不是空格：NUL 不可能出现在这三个输入里，所以
    // ("a b", "c") 和 ("a", "b c") 拼不出同一个串。用空格的话它们会撞成
    // 同一个 event_id——两件不同的事被下游当成同一件，而且没有任何报错。
    //
    // 写成转义而不是裸字节：裸 NUL 会让 grep、diff 和一部分编辑器把整个文件
    // 当成二进制，从此看不见改动。（这一版就是这么来的，改回来了。）
    .update([idempotencyKey, type, sessionKey].join("\u0000"))
    .digest("hex").slice(0, 24)}`;
}

// 公开面用的短哈希。带盐是为了让它不能被反查：session_key 的取值空间不大，
// 不加盐的话，拿到公开页就能用彩虹表把哈希还原成原值。
function publicHash(value, salt) {
  return crypto.createHmac("sha256", String(salt || "cyberboss-public-projection"))
    .update(String(value))
    .digest("hex").slice(0, 16);
}

// 建一条内部事件。
//
// 时间由 canonicalStamp 现算，**不收调用方传进来的一对时间**：收的话，调用方
// 可以传一对互相矛盾的 instant_utc 和 canonical_beijing，而那种矛盾在排查时
// 是最难发现的一类——两个字段各自看都合理。
function makeSessionEvent({
  type,
  mode,
  userScope,
  sessionKey,
  idempotencyKey,
  intent = null,
  status = "accepted",
  publicPayload = {},
  at = new Date(),
} = {}) {
  if (!EVENT_TYPES.includes(type)) {
    throw new RangeError(`unknown event type: ${String(type)}`);
  }
  if (!MODES.includes(mode)) {
    throw new RangeError(`unknown mode: ${String(mode)}`);
  }
  if (!STATUSES.includes(status)) {
    throw new RangeError(`unknown status: ${String(status)}`);
  }
  for (const [name, value] of [["userScope", userScope], ["sessionKey", sessionKey],
    ["idempotencyKey", idempotencyKey]]) {
    if (typeof value !== "string" || !value) {
      throw new TypeError(`${name} required`);
    }
  }
  if (!publicPayload || typeof publicPayload !== "object" || Array.isArray(publicPayload)) {
    throw new TypeError("public payload must be an object");
  }
  assertPublicPayload(publicPayload);
  if (Buffer.byteLength(JSON.stringify(publicPayload), "utf8") > MAX_PUBLIC_PAYLOAD_BYTES) {
    throw new RangeError("public payload too large");
  }
  const stamp = canonicalStamp(at);
  return deepFreeze({
    event_id: eventId({ idempotencyKey, type, sessionKey }),
    idempotency_key: idempotencyKey,
    type,
    mode,
    // 真实身份只在内部事件上。公开面走 publicProjection。
    user_scope: userScope,
    session_key: sessionKey,
    intent: intent === null ? null : String(intent),
    status,
    instant_utc: stamp.instant_utc,
    epoch_ms: stamp.epoch_ms,
    canonical_beijing: stamp.canonical_beijing,
    canonical_zone: stamp.canonical_zone,
    public_payload: clone(publicPayload),
  });
}

// 公开投影（AC-043）。
//
// 白名单式：只有列出来的字段出得去。黑名单式的做法在加字段时会默认放行，
// 而加字段的那个人多半没想过公开面。
const PUBLIC_FIELDS = Object.freeze([
  "event_id", "type", "mode", "intent", "status",
  "instant_utc", "canonical_beijing", "canonical_zone",
]);

function publicProjection(event, { salt = "" } = {}) {
  if (!event || typeof event !== "object") {
    throw new TypeError("event required");
  }
  const out = {};
  for (const field of PUBLIC_FIELDS) {
    if (event[field] !== undefined) {
      out[field] = event[field];
    }
  }
  // 身份只出哈希。公开页要的是「这是同一个人的两件事」，不是「这个人是谁」。
  out.user_scope_hash = publicHash(event.user_scope, salt);
  out.session_key_hash = publicHash(event.session_key, salt);
  out.public_payload = clone(event.public_payload || {});
  // 出库前再查一次。
  //
  // 建事件时查过了，但投影是**另一条**路：以后有人给 publicProjection 加一个
  // 「顺便带上 note」的分支，那一次改动不会经过 makeSessionEvent。
  assertPublicPayload(out);
  return deepFreeze(out);
}

module.exports = {
  EVENT_TYPES,
  FORBIDDEN_PUBLIC_KEYS,
  FORBIDDEN_PUBLIC_VALUE,
  MAX_PUBLIC_PAYLOAD_BYTES,
  MODES,
  PUBLIC_FIELDS,
  STATUSES,
  assertPublicPayload,
  eventId,
  makeSessionEvent,
  publicHash,
  publicProjection,
};
