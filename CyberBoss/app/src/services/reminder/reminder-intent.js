"use strict";

const { BEIJING_ZONE } = require("../time/canonical-time");

// 「我跟他说 1 分钟后提醒我，他没有回话，1 分钟后也没有提醒我。」
//
// 查下来 reminder-queue.json 是空的：模型根本没调 cyberboss_reminder_create。
// 工具在、说明书里也写了「要主动建提醒」，但**模型没调就是没建**——而主人这
// 一句话的意思一点都不含糊。
//
// 所以这条不再交给模型判断。「X 分钟后提醒我 ⋯」在代码里直接解析、直接建、
// 直接确认，零模型调用、零 token、必然生效。模型那条工具路径留着，管更复杂的
// 场景；这一层只保证最普通的那句话一定不落空。
//
// 判据严格一点：**必须同时出现时间和"提醒/叫我"这类动词**才算。宁可漏判让模型
// 接着聊，也不能把「我三点才下班」听成一个闹钟。

const CHINESE_DIGITS = new Map(Object.entries({
  〇: 0, 零: 0, 一: 1, 壹: 1, 二: 2, 两: 2, 贰: 2, 三: 3, 叁: 3, 四: 4, 肆: 4,
  五: 5, 伍: 5, 六: 6, 陆: 6, 七: 7, 柒: 7, 八: 8, 捌: 8, 九: 9, 玖: 9,
}));

const UNIT_MS = Object.freeze({
  秒: 1_000,
  分: 60_000,
  分钟: 60_000,
  小时: 3_600_000,
  钟头: 3_600_000,
  个小时: 3_600_000,
  天: 86_400_000,
  日: 86_400_000,
});

// 「提醒」这类词是必要条件。没有它，任何时间都只是聊天里提到的时间。
const REMIND_VERB = /(提醒|提醒我|叫我|喊我|叫醒|闹钟|记得叫|记得提醒)/;

// 建完之后要从原句里剥掉的开头，剩下的才是「提醒什么」。
const VERB_PREFIX = /^(记得|然后|帮我|麻烦|请)?\s*(提醒我一下|提醒一下我|提醒我|叫醒我|提醒|叫我|喊我|叫醒|记得)\s*(我|一下|要|该|去|把|来)?\s*[,，:：、。!！~～]*\s*/;

const DAY_OFFSET = new Map(Object.entries({
  今天: 0, 今日: 0, 明天: 1, 明日: 1, 后天: 2, 大后天: 3,
}));

// 「下午 3 点」是 15 点。这一层错了，主人会在半夜被叫醒。
const MERIDIEM = new Map(Object.entries({
  凌晨: "am", 早上: "am", 早晨: "am", 上午: "am", 清晨: "am",
  中午: "noon", 晌午: "noon",
  下午: "pm", 傍晚: "pm", 晚上: "pm", 夜里: "pm", 晚: "pm",
}));

const MAX_DELAY_MS = 365 * 86_400_000;

function parseNumber(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    return NaN;
  }
  if (/^\d+$/.test(text)) {
    return Number.parseInt(text, 10);
  }
  // 中文数字，够用到 99：十、十五、二十、二十三。
  if (/^[〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾]+$/.test(text)) {
    const normalized = text.replace(/拾/g, "十");
    const tenAt = normalized.indexOf("十");
    if (tenAt === -1) {
      let value = 0;
      for (const character of normalized) {
        const digit = CHINESE_DIGITS.get(character);
        if (digit === undefined) {
          return NaN;
        }
        value = value * 10 + digit;
      }
      return value;
    }
    const highText = normalized.slice(0, tenAt);
    const lowText = normalized.slice(tenAt + 1);
    const high = highText ? CHINESE_DIGITS.get(highText) : 1;
    const low = lowText ? CHINESE_DIGITS.get(lowText) : 0;
    if (high === undefined || low === undefined) {
      return NaN;
    }
    return high * 10 + low;
  }
  return NaN;
}

// 全角数字和常见的花括号一起洗掉，免得「５分钟后」判不出来。
function normalizeText(value) {
  return String(value || "")
    .replace(/[０-９]/g, (character) => String.fromCharCode(character.charCodeAt(0) - 0xfee0))
    .replace(/[「」『』【】]/g, " ")
    .trim();
}

// ── 相对时间：X 分钟后 / 半小时后 / 两个小时以后 ──────────────

const RELATIVE_PATTERN = new RegExp(
  "(半|\\d+|[〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾]+)"
  + "\\s*(个)?\\s*(分钟|分|秒|小时|钟头|天|日)"
  + "\\s*(之后|以后|后)",
);

function matchRelative(text) {
  const match = text.match(RELATIVE_PATTERN);
  if (!match) {
    return null;
  }
  const unitMs = UNIT_MS[match[3]];
  if (!unitMs) {
    return null;
  }
  const amount = match[1] === "半" ? 0.5 : parseNumber(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) {
    return null;
  }
  // 下限只挡"根本送不到"的情况。「30秒后提醒我」是人话，要认：出站队列每一轮
  // 都会扫一遍到期的，而 resolveLongPollTimeoutMs 见到有提醒待发就把长轮询压到
  // 2 秒——十秒的精度是有的。定得太严，就又变成"说了不算"。
  const delayMs = Math.round(amount * unitMs);
  if (delayMs < 10_000 || delayMs > MAX_DELAY_MS) {
    return null;
  }
  return { delayMs, matched: match[0] };
}

// ── 绝对时间：明天早上 8 点 / 下午 3 点半 / 21:30 ─────────────

const ABSOLUTE_PATTERN = new RegExp(
  "(今天|今日|明天|明日|后天|大后天)?\\s*"
  + "(凌晨|早上|早晨|清晨|上午|中午|晌午|下午|傍晚|晚上|夜里|晚)?\\s*"
  + "(\\d{1,2}|[〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾]+)"
  + "\\s*(?:[点點時时:：])\\s*"
  + "(半|一刻|\\d{1,2}|[〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾]+)?\\s*分?",
);

function matchAbsolute(text, nowParts) {
  const match = text.match(ABSOLUTE_PATTERN);
  if (!match) {
    return null;
  }
  let hour = parseNumber(match[3]);
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) {
    return null;
  }
  let minute = 0;
  if (match[4] === "半") {
    minute = 30;
  } else if (match[4] === "一刻") {
    minute = 15;
  } else if (match[4] !== undefined) {
    minute = parseNumber(match[4]);
  }
  if (!Number.isFinite(minute) || minute < 0 || minute > 59) {
    return null;
  }

  const meridiem = MERIDIEM.get(match[2] || "");
  if (meridiem === "pm" && hour < 12) {
    hour += 12;
  } else if (meridiem === "noon" && hour < 12) {
    hour = hour === 12 ? 12 : hour + 12;
  }
  if (hour > 23) {
    return null;
  }

  let dayOffset = DAY_OFFSET.get(match[1] || "");
  if (dayOffset === undefined) {
    // 没说哪天：今天还没到就今天，已经过了就明天。这是所有人默认的理解。
    dayOffset = (hour > nowParts.hour || (hour === nowParts.hour && minute > nowParts.minute))
      ? 0
      : 1;
  }
  return { hour, minute, dayOffset, matched: match[0] };
}

// ── 主人当地时间 ────────────────────────────────────────────
//
// 服务器跑在 UTC，主人活在北京。这一层错 8 小时，「明天早上 8 点叫我」会变成
// 下午 4 点——比不提醒更糟。

function ownerParts(atMs, timeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date(atMs));
  const pick = (type) => Number(parts.find((part) => part.type === type)?.value);
  return {
    year: pick("year"),
    month: pick("month"),
    day: pick("day"),
    // 午夜会被格式化成 24，归零。
    hour: pick("hour") % 24,
    minute: pick("minute"),
    second: pick("second"),
  };
}

// 给定主人当地的年月日时分，算出对应的绝对毫秒。先按 UTC 猜一个，再用那一刻
// 真实的时区偏移修正——夏令时和历史偏移都靠这一步兜住。
function ownerWallClockToMs({ year, month, day, hour, minute }, timeZone) {
  const guess = Date.UTC(year, month - 1, day, hour, minute, 0, 0);
  const seen = ownerParts(guess, timeZone);
  const seenAsUtc = Date.UTC(
    seen.year, seen.month - 1, seen.day, seen.hour, seen.minute, seen.second, 0,
  );
  return guess + (guess - seenAsUtc);
}

// ── 对外 ───────────────────────────────────────────────────

function parseReminderIntent(rawText, {
  now = Date.now(),
  timeZone = BEIJING_ZONE,
} = {}) {
  const text = normalizeText(rawText);
  if (!text || text.length > 200) {
    return null;
  }
  if (!REMIND_VERB.test(text)) {
    return null;
  }

  const relative = matchRelative(text);
  let dueAtMs = 0;
  let matched = "";
  if (relative) {
    dueAtMs = now + relative.delayMs;
    matched = relative.matched;
  } else {
    const absolute = matchAbsolute(text, ownerParts(now, timeZone));
    if (!absolute) {
      return null;
    }
    const today = ownerParts(now, timeZone);
    dueAtMs = ownerWallClockToMs({
      year: today.year,
      month: today.month,
      day: today.day + absolute.dayOffset,
      hour: absolute.hour,
      minute: absolute.minute,
    }, timeZone);
    matched = absolute.matched;
  }

  // 已经过去的时刻不建。宁可让模型接着聊，也不能建一个立刻就响的假闹钟。
  if (!Number.isFinite(dueAtMs) || dueAtMs - now < 10_000 || dueAtMs - now > MAX_DELAY_MS) {
    return null;
  }

  return {
    dueAtMs,
    body: extractBody(text, matched),
    dueAtLabel: formatDueLabel(dueAtMs, now, timeZone),
  };
}

// 「10 分钟后提醒我喝水」→「喝水」。剥不出来就返回空串，上层会用一句通用的。
function extractBody(text, matched) {
  const rest = text.replace(matched, " ").replace(VERB_PREFIX, "").trim();
  const body = rest
    .replace(VERB_PREFIX, "")
    .replace(/^[,，:：、。!！?？~～\s]+/, "")
    .replace(/[。!！~～\s]+$/, "")
    .trim();
  // 剥完只剩一两个虚字（「吧」「哦」）的，当没有内容。
  return body.length >= 2 && body.length <= 120 ? body : "";
}

function formatDueLabel(dueAtMs, nowMs, timeZone) {
  const due = ownerParts(dueAtMs, timeZone);
  const today = ownerParts(nowMs, timeZone);
  const clock = `${String(due.hour).padStart(2, "0")}:${String(due.minute).padStart(2, "0")}`;
  if (due.year === today.year && due.month === today.month && due.day === today.day) {
    return clock;
  }
  const tomorrow = ownerParts(nowMs + 86_400_000, timeZone);
  if (due.year === tomorrow.year && due.month === tomorrow.month && due.day === tomorrow.day) {
    return `明天 ${clock}`;
  }
  return `${due.month} 月 ${due.day} 日 ${clock}`;
}

// 建完立刻回的那一句。不提「已加入队列」「reminder id」这种东西。
function buildConfirmation({ body, dueAtLabel }) {
  return body
    ? `好，${dueAtLabel} 提醒你${body}。`
    : `好，${dueAtLabel} 叫你一声。`;
}

// 到点发出去的那一句。
function buildDueMessage({ body }) {
  return body ? `到点了，${body}。` : "到点了，你让我这个时候叫你一声。";
}

module.exports = {
  buildConfirmation,
  buildDueMessage,
  extractBody,
  ownerWallClockToMs,
  parseNumber,
  parseReminderIntent,
};
