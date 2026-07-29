"use strict";

// 待办和日程的口令层。和提醒那一层同一个道理：
//
// 「说明书里写了、工具也挂着，但模型没调就是没建。」这已经在提醒上验证过一次
// ——reminder-queue.json 当时是空的。待办比提醒更不能靠运气：提醒漏了主人当场
// 就发现，待办漏了他可能一周后才想起来「我不是记过吗」。
//
// 所以最常用的几句话在代码里直接办：加、看、划掉。零模型、零 token、必然生效。
// 其余复杂的说法照旧交给模型，它可以在聊天里自然地帮忙记——两条路不冲突。
//
// 口令尽量短，主人的原话是「减少关键词输入」。

const { parseReminderIntent } = require("../reminder/reminder-intent");

// ── 看 ──────────────────────────────────────────────────────
// 「待办」「我的待办」「todo」都算。后面不能再跟内容，跟了内容就是要加一条。
const LIST_TODO = /^(我的)?(待办|todo|to-?do|任务清单)(列表|清单)?[?？。！!]?$/i;
const LIST_EVENT = /^(我的)?(日程|日历|安排|calendar)(列表|清单|表)?[?？。！!]?$/i;

// ── 加 ──────────────────────────────────────────────────────
// 「记一下 买菜」「待办 买菜」「加待办 买菜」「提醒事项 买菜」。
// 「记一下」放在最前面：它最短、最像人话，也是主人最可能顺手打的。
const ADD_TODO = /^(记一下|记一笔|记下来|加待办|新待办|待办|todo|加任务)\s*[:：,，]?\s*(.+)$/i;

// ── 划掉 ────────────────────────────────────────────────────
// 「完成 1」「做完了 1」「1 done」「划掉 2」。序号就是列表里显示的那个。
const DONE_TODO = /^(完成|做完了?|搞定|划掉|删掉|done)\s*[:：]?\s*(\d{1,3})\s*[.。]?$/i;
// 「完成」后面不带数字：只有一条的时候就是划掉那一条，多条时要问清楚。
const DONE_BARE = /^(完成|做完了?|搞定|划掉|done)[?？。！!]?$/i;

const MAX_TITLE = 200;

// 返回 null 表示这句话不归这一层管，照旧交给模型。
function parseItemIntent(rawText, { now = Date.now(), timeZone = "Asia/Shanghai" } = {}) {
  const text = String(rawText || "").trim();
  if (!text || text.length > 300) {
    return null;
  }

  if (LIST_TODO.test(text)) {
    return { action: "list", kind: "todo" };
  }
  if (LIST_EVENT.test(text)) {
    return { action: "list", kind: "event" };
  }

  const doneMatch = text.match(DONE_TODO);
  if (doneMatch) {
    return { action: "done", kind: "todo", ordinal: Number.parseInt(doneMatch[2], 10) };
  }
  if (DONE_BARE.test(text)) {
    return { action: "done", kind: "todo", ordinal: null };
  }

  const addMatch = text.match(ADD_TODO);
  if (!addMatch) {
    return null;
  }
  const body = addMatch[2].trim().replace(/[。！!~～\s]+$/, "");
  if (!body || body.length > MAX_TITLE) {
    return null;
  }

  // 「记一下 明天下午3点开会」——带时间的记成日程，不带的记成待办。
  //
  // 复用提醒那一层的时间解析，但那一层要求句子里有「提醒/叫我」这类动词，
  // 这里没有，所以借它的时候补一个。
  //
  // 动词必须**加在前面**：那一层剥标题是从句首剥动词的（「提醒我喝水」→「喝水」）。
  // 加在后面的话「明天下午3点开会 提醒我」剥完剩下的是「开会 提醒我」，那三个字
  // 会跟着进日程标题，主人在页面上看到的就是「开会 提醒我」。
  const timed = parseReminderIntent(`提醒我${body}`, { now, timeZone });
  if (timed) {
    return {
      action: "add",
      kind: "event",
      title: timed.body || body,
      dueAtMs: timed.dueAtMs,
      dueAtLabel: timed.dueAtLabel,
    };
  }
  return { action: "add", kind: "todo", title: body };
}

// ── 回话 ────────────────────────────────────────────────────
//
// 都短，像微信，不像报表。列表最多列 10 条——微信里一屏放不下更多，而且
// 一次甩 30 条待办给一个 ADHD 的人，等于什么都没给他。

const KIND_LABEL = Object.freeze({ todo: "待办", event: "日程" });

function buildAddedMessage(item) {
  return item.kind === "event"
    ? `记下了：${item.title}（${item.dueAtLabel}）`
    : `记下了：${item.title}`;
}

function buildListMessage(kind, items, { formatTime = (value) => value } = {}) {
  const label = KIND_LABEL[kind] || "待办";
  if (!items.length) {
    return kind === "event" ? "日程是空的。" : "待办是空的，挺好。";
  }
  const shown = items.slice(0, 10);
  const lines = shown.map((item, index) => {
    const when = item.dueAt ? `（${formatTime(item.dueAt)}）` : "";
    return `${index + 1}. ${item.title}${when}`;
  });
  const more = items.length > shown.length
    ? `\n还有 ${items.length - shown.length} 条。`
    : "";
  const hint = kind === "todo" ? "\n\n做完哪条就回「完成 序号」。" : "";
  return `${label}：\n${lines.join("\n")}${more}${hint}`;
}

function buildDoneMessage(item) {
  return item ? `划掉了：${item.title}` : "";
}

function buildDoneFailedMessage(openCount) {
  if (!openCount) {
    return "待办本来就是空的。";
  }
  return `要划掉哪一条？回「完成 序号」，现在有 ${openCount} 条。`;
}

module.exports = {
  buildAddedMessage,
  buildDoneFailedMessage,
  buildDoneMessage,
  buildListMessage,
  parseItemIntent,
};
