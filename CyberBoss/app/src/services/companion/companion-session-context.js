"use strict";

// Companion 的稳定会话与有界上下文（CB9-120 / AC-004、AC-038、AC-044）。
//
// 在此之前，普通用户这条路是**完全无状态**的：runUserModelTurn 只传了
// contextToken（微信的回复凭据），一句对话上下文都没有。所以「第二轮引用第一轮
// 已确认的事实」在实现上不可能成立——每一轮模型都从零开始。这正是 v0.0.0.9
// 说的「持续 Agent 的核心语义被稀释」。
//
// 三条不变量，顺序不能反：
//   1. session_key 由 user_scope 推出，且**跨重启不变**（AC-044）。不能用随机
//      数或内存 Map：进程一重启，这个人就换了个 Agent。
//   2. 上下文只装**这个人自己的**行。过滤发生在装配处，不在读取处——读的地方
//      忘了带条件是这个仓最熟悉的坏法。
//   3. 上下文有硬上限（条数 + 字节）。OVH 那台机器上一个失控的上下文能把整个
//      队列拖死；宁可少带几条旧的，也不能让一个人的会话吃掉所有人的额度。
//
// 改编自任务包 v0.0.0.9 Starter Kit 的 runtime/companion-session-context.js，
// 语义保持一致（它的 9 条冻结测试是本节点的 Oracle）。

const crypto = require("node:crypto");

// 逐出顺序是**冻结的**：先扔最旧的对话轮次，最后才动已确认事实。
// 身份（user_scope/session_key）和能力策略永远不参与逐出。
const EVICTION_ORDER = Object.freeze([
  "turns",
  "recent_timeline",
  "unresolved_items",
  "accepted_facts",
]);

// Companion 永远碰不到的东西。写在上下文里是给模型看的**第二道**提醒；
// 真正的闸门在 UserContext 的能力模型和 tool-host，不靠这行字。
const FORBIDDEN_CAPABILITIES = Object.freeze([
  "codex", "claude_code", "workspace", "tools", "shell", "mcp", "approval",
]);

const DEFAULTS = Object.freeze({
  maxTurns: 24, maxFacts: 32, maxItems: 24, maxTimeline: 24,
  maxItemBytes: 8 * 1024, maxContextBytes: 64 * 1024,
});

function stableSessionKey(userScope, secret) {
  // secret 用运行库那把 identity key（已经是 32 字节且只有主人读得到）。
  // 用 HMAC 而不是明文拼接：session_key 会进日志和证据，不能反推出 user_id。
  if (typeof userScope !== "string" || !userScope
    || typeof secret !== "string" || secret.length < 16) {
    throw new TypeError("non-empty userScope and secret of at least 16 characters required");
  }
  return `comp_${crypto.createHmac("sha256", secret).update(userScope).digest("hex").slice(0, 32)}`;
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

function boundedPositiveInteger(value, fallback, maximum = 100) {
  return Number.isInteger(value) && value >= 0 ? Math.min(value, maximum) : fallback;
}

function byteLength(value) {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

function buildBoundedContext({
  userScope,
  sessionKey,
  turns = [],
  acceptedFacts = [],
  unresolvedItems = [],
  timeline = [],
  maxTurns = DEFAULTS.maxTurns,
  maxFacts = DEFAULTS.maxFacts,
  maxItems = DEFAULTS.maxItems,
  maxTimeline = DEFAULTS.maxTimeline,
  maxItemBytes = DEFAULTS.maxItemBytes,
  maxContextBytes = DEFAULTS.maxContextBytes,
} = {}) {
  if (typeof userScope !== "string" || !userScope
    || typeof sessionKey !== "string" || !sessionKey) {
    throw new TypeError("scoped session required");
  }
  const itemLimit = boundedPositiveInteger(maxItemBytes, DEFAULTS.maxItemBytes, 64 * 1024);
  const contextLimit = boundedPositiveInteger(maxContextBytes, DEFAULTS.maxContextBytes, 256 * 1024);
  if (itemLimit === 0 || contextLimit === 0) {
    throw new TypeError("context byte limits must be positive");
  }

  // 过滤在这里发生，一次。每个桶都必须过同一道 user_scope 判断——漏掉一个桶
  // 就是把别人的东西塞进这个人的上下文，而且模型不会告诉你。
  const clean = (items, limit, fallback) => {
    const count = boundedPositiveInteger(limit, fallback);
    if (count === 0 || !Array.isArray(items)) {
      return [];
    }
    return items
      .filter((item) => item && item.user_scope === userScope)
      .slice(-count)
      .map(clone)
      .filter((item) => byteLength(item) <= itemLimit);
  };

  const context = {
    user_scope: userScope,
    session_key: sessionKey,
    mode: "COMPANION",
    turns: clean(turns, maxTurns, DEFAULTS.maxTurns),
    accepted_facts: clean(acceptedFacts, maxFacts, DEFAULTS.maxFacts),
    unresolved_items: clean(unresolvedItems, maxItems, DEFAULTS.maxItems),
    recent_timeline: clean(timeline, maxTimeline, DEFAULTS.maxTimeline),
    forbidden_capabilities: [...FORBIDDEN_CAPABILITIES],
  };

  // 按冻结优先级逐出，直到落到字节上限之下。身份和能力策略不参与。
  while (byteLength(context) > contextLimit) {
    const bucket = EVICTION_ORDER.find((key) => context[key].length > 0);
    if (!bucket) {
      throw new Error("context identity exceeds byte ceiling");
    }
    context[bucket].shift();
  }
  return deepFreeze(context);
}

module.exports = {
  DEFAULTS,
  EVICTION_ORDER,
  FORBIDDEN_CAPABILITIES,
  buildBoundedContext,
  deepFreeze,
  stableSessionKey,
};
