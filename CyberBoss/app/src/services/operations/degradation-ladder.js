"use strict";

// 资源不够时按固定顺序关东西（CB9-320 / AC-009、AC-031、NFR-001）。
//
// AC-031 把顺序写死了：
//   访客主动关心 → Owner 脉冲 → 媒体/浏览器 → 访客模型 → Owner 新任务排队
//
// 顺序不是随便排的，它是按「关掉之后谁会发现」排的：
//
//   访客主动关心  —— 关了没人知道。它本来就是可有可无的问候。
//   Owner 脉冲    —— 主人可能会注意到今天它没主动找他，但他随时能自己开口。
//   媒体/浏览器   —— 图片和网页是重的（下载、转码、无头浏览器），而且**有替代**：
//                    用户可以先把话说清楚，稍后再发图。
//   访客模型      —— 到这一层访客就明显感觉到了：他问话没有智能回答。但确定性
//                    功能（记待办、设提醒、看时间线）还在，他不是完全用不了。
//   Owner 新任务  —— 最后才动主人，而且是**排队**不是拒绝：他的活儿一件不丢，
//                    只是要等。
//
// 反过来排（先停主人的活儿去保访客的问候）在任何一个压力等级上都是错的。
//
// 这个模块是**纯函数**，一个 require 都不往外接。
// 理由和 resource-gate 一样：从「机器快撑不住了」这个判断到「调一次模型」之间
// 不能存在任何路径——自愈的时候调模型，正是压垮它的最后一根稻草（AC-031 明写
// 「自愈模型调用=0」）。

// 冻结的关闭顺序。数组下标就是关闭的先后。
const DEGRADATION_ORDER = Object.freeze([
  Object.freeze({
    id: "guest_proactive",
    label: "访客主动关心",
    // 关掉之后用户侧的表现。这句会进 Status 和运维日志，不进用户对话——
    // 用户不需要知道「系统降级了」，他只需要东西还能用。
    effect: "不再主动找访客说话；他们发消息照常回",
  }),
  Object.freeze({
    id: "owner_pulse",
    label: "Owner 脉冲",
    effect: "不再主动找主人；主人开口照常回",
  }),
  Object.freeze({
    id: "media_and_browser",
    label: "媒体与浏览器",
    effect: "暂不处理图片、文件和网页抓取；文字对话不受影响",
  }),
  Object.freeze({
    id: "guest_model",
    label: "访客模型调用",
    effect: "访客的模型回复排队；记待办、设提醒、看时间线这些照常",
  }),
  Object.freeze({
    id: "owner_new_tasks",
    label: "Owner 新任务",
    effect: "主人的新任务排队等待，不丢；正在跑的那个不打断",
  }),
]);

const CAPABILITY_IDS = Object.freeze(DEGRADATION_ORDER.map((step) => step.id));

// 无论降到第几级都不许关的东西。
//
// FR-009 的原话：「共享模型资源不足时**保持**笔记、提醒、Timeline、查询等确定性
// 能力」。这些不花模型钱，也不吃内存——关掉它们既省不下什么，又让用户彻底没得用。
const ALWAYS_ON = Object.freeze([
  "notes",        // 记一下
  "reminders",    // 提醒我
  "timeline",     // 时间线
  "queries",      // 我的记忆、最近 7 天
  "diary",        // 日记（零模型）
  "location",     // 我在哪 / 我到纽约了
]);

// 压力等级 → 关到第几级。
//
// 等级是**外面算出来的**（resource-gate 给的 reasonCode 数量、队列深度等），
// 这里只负责把等级翻译成一份关闭清单。分开是为了让顺序这件事能单独测：
// 揉在一起的话，改一次阈值就要重测整条顺序。
// 每一级对应关掉阶梯上的前几项，**一一对应**。
//
// 第一版写的是 0/1/3/5，跳过了 2 和 4——也就是「只关到媒体/浏览器」和「只关到
// 访客模型」这两个状态永远到不了。阶梯上白写了两级，而且从 elevated 掉到 high
// 会一次关掉三样，用户的体感是断崖而不是逐步变慢。
const LEVELS = Object.freeze({
  normal: 0,        // 什么都不关
  low: 1,           // 访客主动关心
  elevated: 2,      // + Owner 脉冲
  high: 3,          // + 媒体/浏览器
  severe: 4,        // + 访客模型
  critical: 5,      // + Owner 新任务排队
});

function normalizeLevel(level) {
  return Object.prototype.hasOwnProperty.call(LEVELS, level) ? level : "normal";
}

// 这个等级下，哪些能力被关了。
function disabledAt(level) {
  const depth = LEVELS[normalizeLevel(level)];
  return Object.freeze(DEGRADATION_ORDER.slice(0, depth).map((step) => step.id));
}

// 这个能力现在能不能用。
function allows(level, capabilityId) {
  const id = String(capabilityId || "");
  if (ALWAYS_ON.includes(id)) {
    return true;
  }
  if (!CAPABILITY_IDS.includes(id)) {
    // 不在阶梯上的能力默认放行。挡一个我们没想过的东西，比放行它更容易造成
    // 「某个功能莫名其妙不能用了，而且没人知道为什么」。
    return true;
  }
  return !disabledAt(level).includes(id);
}

// 给运维看的一份说明。**不进用户对话**。
function describe(level) {
  const normalized = normalizeLevel(level);
  const off = disabledAt(normalized);
  return Object.freeze({
    level: normalized,
    disabled: off,
    steps: Object.freeze(DEGRADATION_ORDER
      .filter((step) => off.includes(step.id))
      .map((step) => Object.freeze({ ...step }))),
    always_on: [...ALWAYS_ON],
  });
}

// 用户在被限流时看到的那一句（AC-009）。
//
// 三条硬要求：
//   一、中文；
//   二、说清楚「还能做什么」，不是只说「不行」；
//   三、**不出现任何配置密钥的指令**——AC-009 明写「页面和微信不出现密钥配置
//       指令」。一个新手在系统最忙的时候被要求去弄一个 API key，是这条 AC 唯一
//       要挡的东西。
function throttleNotice({ owner = false } = {}) {
  return owner
    ? "这会儿有点忙，你这条我排上了，忙完马上办。记东西、设提醒这些照常。"
    : "这会儿人有点多，你这句我排上了，一会儿就回你。要记什么、要提醒，现在说照样管用。";
}

// 共享额度用完时的那一句。同样不许提密钥。
function budgetExhaustedNotice() {
  return "今天的智能回复用量用完了，明天会自动恢复。这期间记东西、设提醒、看时间线都照常。";
}

module.exports = {
  ALWAYS_ON,
  CAPABILITY_IDS,
  DEGRADATION_ORDER,
  LEVELS,
  allows,
  budgetExhaustedNotice,
  describe,
  disabledAt,
  normalizeLevel,
  throttleNotice,
};
