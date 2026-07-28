"use strict";

// 普通用户的确定性中文口令，在到达模型之前就处理掉。
//
// CB-720/CB-740 把日记、提醒、时间线、行为统计都建好并证明过了，但它们从来没被
// 一条真实微信消息碰到过。这个模块就是那个锚点。
//
// 为什么这些不交给模型：一条「记一下 今天很累」应该确定性地落进数据库，而不是
// 看模型这次心情如何。走这里的每一条都 modelCalls: 0——省钱是次要的，主要是
// 用户说"记一下"就必须真的记下来。

const {
  UserCompanionService,
} = require("../services/companion/user-companion-service");
const {
  EVENT_TYPES,
  SqliteActivityAggregator,
  utcDay,
} = require("../services/analytics/activity-aggregator");
const { renderTemplate } = require("../services/checkin/deterministic-checkin");
const { resolveNoviceCommand } = require("../services/commands/novice-command-map");

// 带参数的口令用前缀匹配；不带参数的交给 CB-730 的 novice-command-map，
// 那张表已经收录了用户的各种日常说法。
const PREFIXES = Object.freeze([
  { action: "diary.write", prefixes: ["记一下", "记录一下", "帮我记", "写日记"] },
  { action: "reminder.create", prefixes: ["提醒我", "记得提醒我", "叫我"] },
]);

const MESSAGES = Object.freeze({
  DIARY_SAVED: "记下了 ✓",
  DIARY_EMPTY: "要记什么？像这样发给我：记一下 今天跑了五公里",
  REMINDER_SAVED: (title, when) => `好，${when}提醒你「${title}」✓`,
  REMINDER_EMPTY: "要提醒什么？像这样发给我：提醒我 明天9点 交房租",
  REMINDER_NONE: "现在没有待办的提醒。",
  TIMELINE_EMPTY: "还没有记录。发「记一下 ……」就能开始。",
  CHECKIN_ON: "好，我会偶尔主动问候你。不想被打扰随时说「别再问我」。",
  CHECKIN_OFF: "好，以后不主动打扰你了。想恢复就说「可以问我」。",
  WEEK_EMPTY: "最近七天还没有记录。",
});

// 中文时间的确定性解析。只认这几种明确写法；看不懂就照实说看不懂，而不是
// 猜一个时间然后在错的时候提醒用户——那比不提醒更糟。
const RELATIVE_DAYS = Object.freeze({ 今天: 0, 明天: 1, 后天: 2, 大后天: 3 });

function parseChineseDueAt(text, nowMs) {
  const source = String(text || "");
  const dayMatch = source.match(/(今天|明天|后天|大后天)/);
  const hourMatch = source.match(/(\d{1,2})\s*[:：点时]\s*(\d{1,2})?/);
  if (!hourMatch) {
    return null;
  }
  const hour = Number(hourMatch[1]);
  const minute = Number(hourMatch[2] || 0);
  if (!Number.isInteger(hour) || hour > 23 || !Number.isInteger(minute) || minute > 59) {
    return null;
  }
  // 用户说的是本地时间。这里按东八区解释——微信侧的展示也用同一个时区，
  // 两边不一致会让"9点"变成一个用户没说过的时刻。
  const offsetMinutes = 480;
  const local = new Date(nowMs + offsetMinutes * 60_000);
  const dayOffset = dayMatch ? RELATIVE_DAYS[dayMatch[1]] : 0;
  const due = new Date(local);
  due.setUTCDate(due.getUTCDate() + dayOffset);
  due.setUTCHours(hour, minute, 0, 0);
  let dueMs = due.getTime() - offsetMinutes * 60_000;
  // 没写哪天而时刻已经过去，指的是明天的同一时刻。
  if (!dayMatch && dueMs <= nowMs) {
    dueMs += 24 * 60 * 60 * 1000;
  }
  return dueMs;
}

function formatWhen(dueAtMs, nowMs) {
  const offsetMinutes = 480;
  const due = new Date(dueAtMs + offsetMinutes * 60_000);
  const now = new Date(nowMs + offsetMinutes * 60_000);
  const sameDay = due.toISOString().slice(0, 10) === now.toISOString().slice(0, 10);
  const clock = `${String(due.getUTCHours()).padStart(2, "0")}:${String(due.getUTCMinutes()).padStart(2, "0")}`;
  return sameDay ? `今天 ${clock} ` : `${due.toISOString().slice(5, 10).replace("-", "月")}日 ${clock} `;
}

function matchPrefix(text) {
  const trimmed = String(text || "").trim();
  for (const entry of PREFIXES) {
    for (const prefix of entry.prefixes) {
      if (trimmed.startsWith(prefix)) {
        return { action: entry.action, rest: trimmed.slice(prefix.length).trim() };
      }
    }
  }
  return null;
}

class UserCompanionTurn {
  constructor({ database, now = () => Date.now() }) {
    this.companion = new UserCompanionService({
      database,
      now: () => new Date(now()),
    });
    this.analytics = new SqliteActivityAggregator({
      database,
      now: () => new Date(now()),
    });
    this.database = database;
    this.now = now;
  }

  // 返回一条要回复的文字，或者 null 表示"这条不是我的活儿，交给模型"。
  // 任何一条走到这里的消息都不会花钱。
  handle(userContext, text) {
    const nowMs = this.now();
    const prefixed = matchPrefix(text);
    if (prefixed) {
      return this.#handlePrefixed(userContext, prefixed, nowMs);
    }
    const action = resolveNoviceCommand(text);
    if (!action) {
      return null;
    }
    switch (action) {
      // 动作名来自 CB-730 的 novice-command-map，不是我另起的一套。
      // 「我的记忆」「我的资料」都归到同一条时间线上——用户不区分这两个词。
      case "portal.memory":
      case "portal.profile":
        return this.#timeline(userContext);
      case "reminder.create":
        return Object.freeze({ text: MESSAGES.REMINDER_EMPTY, modelCalls: 0 });
      case "checkin.disable":
        this.companion.setCheckinEnabled(userContext, false);
        return Object.freeze({ text: MESSAGES.CHECKIN_OFF, modelCalls: 0 });
      case "checkin.enable":
        this.companion.setCheckinEnabled(userContext, true);
        return Object.freeze({ text: MESSAGES.CHECKIN_ON, modelCalls: 0 });
      case "analytics.week":
        return this.#week(userContext);
      default:
        // 其余口令（设置、帮助、导出、删除）在 admission 那一层已经处理过了。
        return null;
    }
  }

  #handlePrefixed(userContext, { action, rest }, nowMs) {
    if (action === "diary.write") {
      if (!rest) {
        return Object.freeze({ text: MESSAGES.DIARY_EMPTY, modelCalls: 0 });
      }
      this.companion.writeDiary(userContext, { text: rest });
      this.#record(userContext, "profile_changed", nowMs);
      return Object.freeze({ text: MESSAGES.DIARY_SAVED, modelCalls: 0 });
    }
    // reminder.create
    const dueAtMs = parseChineseDueAt(rest, nowMs);
    if (dueAtMs === null) {
      return Object.freeze({ text: MESSAGES.REMINDER_EMPTY, modelCalls: 0 });
    }
    const title = rest
      .replace(/(今天|明天|后天|大后天)/, "")
      .replace(/\d{1,2}\s*[:：点时]\s*\d{0,2}\s*分?/, "")
      .trim();
    if (!title) {
      return Object.freeze({ text: MESSAGES.REMINDER_EMPTY, modelCalls: 0 });
    }
    this.companion.createReminder(userContext, {
      title,
      dueAt: new Date(dueAtMs).toISOString(),
    });
    this.#record(userContext, "reminder_completed", nowMs);
    return Object.freeze({
      text: MESSAGES.REMINDER_SAVED(title, formatWhen(dueAtMs, nowMs)),
      modelCalls: 0,
    });
  }

  #timeline(userContext) {
    const rows = this.companion.timeline(userContext, { limit: 10 });
    if (!rows.length) {
      return Object.freeze({ text: MESSAGES.TIMELINE_EMPTY, modelCalls: 0 });
    }
    const lines = ["最近的记录："];
    for (const row of rows) {
      let value = {};
      try {
        value = JSON.parse(row.value_json);
      } catch {
        value = {};
      }
      const when = String(row.updated_at || "").slice(5, 16).replace("T", " ");
      lines.push(`  ${when}  ${value.title || value.text || "(空)"}`);
    }
    return Object.freeze({ text: lines.join("\n"), modelCalls: 0 });
  }

  #week(userContext) {
    const rows = this.analytics.readForUser(userContext.userId, { limit: 7 });
    if (!rows.length) {
      return Object.freeze({ text: MESSAGES.WEEK_EMPTY, modelCalls: 0 });
    }
    // readForUser 返回的是 { day, ...已解析的指标 }，metrics_json 已经在那边
    // 展开过了。这里再解析一次只会得到空对象，统计就会永远显示为零。
    const totals = new Map();
    for (const row of rows) {
      for (const [name, count] of Object.entries(row)) {
        if (name === "day") {
          continue;
        }
        const value = Number(count);
        if (Number.isFinite(value) && value > 0) {
          totals.set(name, (totals.get(name) || 0) + value);
        }
      }
    }
    // 键名来自聚合器的 EVENT_TYPES，这里只负责翻成中文。没收录的键原样显示，
    // 不隐藏——统计里出现了没见过的东西，用户有权看见。
    const label = {
      messages: "聊天",
      aiTurns: "AI 回复",
      imports: "导入",
      remindersCompleted: "提醒",
      profileChanges: "记录",
      checkinsAnswered: "问候回应",
    };
    const lines = [`最近 ${rows.length} 天：`];
    for (const [name, count] of totals) {
      lines.push(`  ${label[name] || name} ${count} 次`);
    }
    return Object.freeze({ text: lines.join("\n"), modelCalls: 0 });
  }

  // 当天计数 +1。
  //
  // 这里刻意不调 rebuildForUser：它是"用完整事件流重算这个用户的全部历史"，
  // 每来一条消息就拿单条事件调它，会把之前所有天的统计删光。真正的增量写法
  // 是对当天那一行做 upsert——按天分组和字段命名这两条规则仍然用聚合器自己的
  // utcDay 和 EVENT_TYPES，不另写一套。
  //
  // 统计写失败会被吞掉：它是附带产物，不该把用户刚做成的那件事一起带崩。
  #record(userContext, eventType, nowMs) {
    const field = EVENT_TYPES[eventType];
    if (!field) {
      return;
    }
    try {
      const day = utcDay(nowMs);
      const stamp = new Date(nowMs).toISOString();
      const existing = this.database
        .prepare("SELECT metrics_json FROM activity_daily WHERE user_id=? AND day=?")
        .get(userContext.userId, day);
      let metrics = {};
      if (existing) {
        try {
          metrics = JSON.parse(existing.metrics_json) || {};
        } catch {
          metrics = {};
        }
      }
      metrics[field] = (Number(metrics[field]) || 0) + 1;
      this.database
        .prepare(
          `INSERT INTO activity_daily(user_id, day, metrics_json, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, day)
           DO UPDATE SET metrics_json=excluded.metrics_json, updated_at=excluded.updated_at`,
        )
        .run(userContext.userId, day, JSON.stringify(metrics), stamp);
    } catch {
      // 统计写不进去不影响用户刚才那件事已经做成了。
    }
  }

  recordMessage(userContext, nowMs = this.now()) {
    this.#record(userContext, "message", nowMs);
  }

  // 每一轮运维循环调用一次：为开启了主动问候的用户算出该不该发、发什么。
  // 全程确定性，一次模型调用都没有。
  planProactive(userContext, { lastCheckinMs = null } = {}) {
    const decision = this.companion.planProactiveMessage(userContext, {
      nowMs: this.now(),
      lastCheckinMs,
    });
    if (!decision.send) {
      return decision;
    }
    return Object.freeze({
      ...decision,
      text: renderTemplate(decision.slot, decision.values || {}),
    });
  }
}

module.exports = {
  MESSAGES,
  PREFIXES,
  UserCompanionTurn,
  formatWhen,
  parseChineseDueAt,
};
