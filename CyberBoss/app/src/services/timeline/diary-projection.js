"use strict";

// 日记是**投影**，不是生成（CB9-430 / AC-019、FR-019）。
//
// FR-019 的原话：「日记使用已发生事件、Timeline 和回执生成，不额外调用模型；
// 无新事件不产生空日记。」
//
// 两条各挡一件事：
//
//   零模型 —— 一天写一次日记，一次一个模型调用，看起来不多。但日记是**每个人
//     每天**都要写的：五个人就是五次，而它们全都花在「把今天发生过的事重述
//     一遍」上——那些事系统自己全知道。更糟的是模型会编：它会补出一件今天没
//     发生过的事，而日记正是主人日后拿来回忆的东西。
//
//   无新事件不产空文件 —— 一个人今天没说过话，日记里就不该出现「2026-08-02」
//     这个标题下面跟着一片空白。空条目会让「他那天是不是没用」和「那天没记
//     上」变得分不清，而且备份和同步会每天多一次无谓的变更。
//
// 这个模块是**纯函数**，一个 require 都不往外接（除了事件模型自己的常量）。
// 理由和降级阶梯一样：从「写日记」到「调模型」之间不能存在任何路径。有测试
// 扫源码钉住这一点——"零模型" 靠的不是「我们没调」，是「够不着」。

const { EVENT_TYPES } = require("./session-event");

// 哪些事件值得写进日记。
//
// **不是全部**。投递、降级、恢复这些是运维事件：主人回头翻日记想看的是「我那
// 天做了什么」，不是「那天有一次投递重试」。把它们写进去，真正有用的两三条会
// 被淹掉。
const DIARY_WORTHY = Object.freeze([
  "message",           // 说了话
  "task",              // 办了事
  "reminder_created",  // 定了个提醒
  "reminder_fired",    // 提醒响了
  "approval",          // 批了什么
  "media",             // 发了图或文件
]);

// 每一类在日记里怎么念。
//
// 写死的中文短语，不是模板字符串拼变量——变量拼出来的句子在数量为 1 和为 0
// 时读起来都很别扭（「今天你说了 1 次话」），而日记是给人读的。
const PHRASES = Object.freeze({
  message: (n) => (n === 1 ? "聊了一次" : `聊了 ${n} 次`),
  task: (n) => (n === 1 ? "办了一件事" : `办了 ${n} 件事`),
  reminder_created: (n) => (n === 1 ? "定了一个提醒" : `定了 ${n} 个提醒`),
  reminder_fired: (n) => (n === 1 ? "有一个提醒响了" : `有 ${n} 个提醒响了`),
  approval: (n) => (n === 1 ? "批了一件事" : `批了 ${n} 件事`),
  media: (n) => (n === 1 ? "发了一个文件" : `发了 ${n} 个文件`),
});

// 这一天这个人的日记。
//
// 返回 null 表示**什么都不该写**——不是返回一个空条目让调用方自己判断。
// 让调用方判断的话，总有一个调用方会忘，而忘掉的后果是每天多一个空文件。
function projectDiary({ events = [], userScope = "", date = "" } = {}) {
  const scope = typeof userScope === "string" ? userScope.trim() : "";
  const day = typeof date === "string" ? date.trim() : "";
  if (!scope || !day) {
    return null;
  }
  // 只投影**这个人**这一天的事件。过滤在这里发生一次——读的地方忘了带条件
  // 是这个仓最熟悉的坏法。
  const mine = (Array.isArray(events) ? events : []).filter((event) => (
    event
    && event.user_scope === scope
    && typeof event.canonical_beijing === "string"
    && event.canonical_beijing.slice(0, 10) === day
    && DIARY_WORTHY.includes(event.type)
  ));
  if (mine.length === 0) {
    // 无新事件 → 一个字都不写。AC-019 的「文件/事实/提交变化数=0」。
    return null;
  }

  const counts = new Map();
  for (const event of mine) {
    counts.set(event.type, (counts.get(event.type) || 0) + 1);
  }
  // 按 DIARY_WORTHY 的顺序念，不按出现顺序——同一天的两次投影必须给出
  // 一模一样的文本，否则「没变化」判不出来，每天都会多一次提交。
  const parts = DIARY_WORTHY
    .filter((type) => counts.has(type))
    .map((type) => PHRASES[type](counts.get(type)));

  // 时间跨度用第一件和最后一件事的北京时间。排序按 epoch_ms，不按渲染出来的
  // 字符串——字符串排序在跨时区的事件上会排错。
  const sorted = [...mine].sort((a, b) => (a.epoch_ms || 0) - (b.epoch_ms || 0));
  const from = sorted[0].canonical_beijing.slice(11, 16);
  const to = sorted[sorted.length - 1].canonical_beijing.slice(11, 16);

  return Object.freeze({
    date: day,
    user_scope: scope,
    event_count: mine.length,
    // 零模型的证据。这个字段进证据和 Status——它是这条 AC 在运维面唯一
    // 看得见的东西。
    model_calls: 0,
    span: from === to ? from : `${from}–${to}`,
    body: `${from === to ? from : `${from}–${to}`}　${parts.join("，")}。`,
    // 投影用到的事件 id，按序。日后要追「日记里这句话是从哪来的」，靠它。
    source_event_ids: Object.freeze(sorted.map((event) => event.event_id)),
  });
}

// 同一份事件投影两次，结果必须一模一样。
//
// 不一样的话，「今天有没有新东西」就判不出来——每天都会写一次、提交一次，
// 而备份和同步跟着每天多一次无谓的变更。
function isStable(events, userScope, date) {
  const a = projectDiary({ events, userScope, date });
  const b = projectDiary({ events, userScope, date });
  return JSON.stringify(a) === JSON.stringify(b);
}

// 这一天相比已有的那份有没有变化。
//
// 比的是**正文**，不是时间戳：只比时间戳的话，每次投影都是「变了」。
function hasChanged(projected, existingBody) {
  if (!projected) {
    // 没有新事件就是没变化——哪怕之前有过内容。
    // 反过来（当成「变成空了」去覆盖）会把已经写好的日记擦掉。
    return false;
  }
  return String(existingBody || "").trim() !== projected.body.trim();
}

module.exports = {
  DIARY_WORTHY,
  PHRASES,
  hasChanged,
  isStable,
  projectDiary,
};
