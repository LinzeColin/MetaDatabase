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

// 这个墙上时间在这个时区里到底存不存在、是不是出现了两次（AC-016）。
//
// 夏令时一年制造两种畸形时刻：
//   跳时（gap）——那一小时**不存在**。悉尼 2026-10-04 没有 02:00。
//   重复（fold）——那一小时出现**两次**。纽约 2026-11-01 有两个 01:30。
//
// ownerWallClockToMs 对这两种都会安静地给一个数：gap 时给的是跳之前那一刻
// （用户说 02:00，闹钟落在 01:00，早一小时），fold 时给的是两次里的某一次。
// 「安静地早一小时」是最坏的结果——用户没有任何办法发现，直到闹钟在错的时候响。
//
// 所以这里把它判出来交给上层：不存在就去问，重复就说清楚是哪一次。
function classifyWallClock({ year, month, day, hour, minute }, timeZone) {
  const atMs = ownerWallClockToMs({ year, month, day, hour, minute }, timeZone);
  const back = ownerParts(atMs, timeZone);
  // 回读对不上＝这个墙上时间不存在。
  if (back.year !== year || back.month !== month || back.day !== day
    || back.hour !== hour || back.minute !== minute) {
    return { kind: "nonexistent", atMs, rendered: back };
  }
  // 同一个墙上时间的另一个候选。**两个方向都要找**：ownerWallClockToMs 给的
  // 可能是较早那次也可能是较晚那次，只往一边找就会漏掉一半的情况——而漏掉的
  // 那一半在测试里表现为 ambiguous=false，看起来像「这天没问题」。
  // 半小时和 45 分钟的偏移也要试：不是所有时区都按整小时切。
  for (const deltaMs of [-3600_000, 3600_000, -1800_000, 1800_000, -2700_000, 2700_000]) {
    const other = atMs + deltaMs;
    const p = ownerParts(other, timeZone);
    if (p.year === year && p.month === month && p.day === day
      && p.hour === hour && p.minute === minute) {
      // 两个都对：取**较早**的那一次（和大多数日历软件一致），并把这件事说出来。
      const earlier = Math.min(atMs, other);
      return { kind: "ambiguous", atMs: earlier, alternateMs: Math.max(atMs, other) };
    }
  }
  return { kind: "ok", atMs };
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
  let ambiguous = false;
  if (relative) {
    dueAtMs = now + relative.delayMs;
    matched = relative.matched;
  } else {
    const absolute = matchAbsolute(text, ownerParts(now, timeZone));
    if (!absolute) {
      return null;
    }
    const today = ownerParts(now, timeZone);
    // 先归一到一个真实日期（day + offset 可能溢出月末），再判 DST。
    const normalized = ownerParts(ownerWallClockToMs({
      year: today.year,
      month: today.month,
      day: today.day + absolute.dayOffset,
      hour: 12,
      minute: 0,
    }, timeZone), timeZone);
    const classified = classifyWallClock({
      year: normalized.year,
      month: normalized.month,
      day: normalized.day,
      hour: absolute.hour,
      minute: absolute.minute,
    }, timeZone);
    // 不存在的时刻不建闹钟，交给上层去问一句（AC-016）。
    // 安静地挪一小时是最坏的处理：用户没有任何办法发现，直到它在错的时候响。
    if (classified.kind === "nonexistent") {
      return {
        needsConfirmation: true,
        reason: "nonexistent_local_time",
        askedFor: `${String(absolute.hour).padStart(2, "0")}:${String(absolute.minute).padStart(2, "0")}`,
        timeZone,
      };
    }
    dueAtMs = classified.atMs;
    if (classified.kind === "ambiguous") {
      ambiguous = true;
    }
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
    // 那一小时出现了两次，取的是较早的一次——得说出来，否则用户以为是另一次。
    ambiguous,
    ...(ambiguous ? { offsetLabel: utcOffsetLabel(dueAtMs, timeZone) } : {}),
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
  const local = relativeLabel(dueAtMs, nowMs, timeZone);
  // 跨时区的人要同时看到北京时间（AC-041）。
  //
  // 只给当地时间的话，一个在悉尼的人和主人约「明天 14:00」，两个人说的是两个
  // 时刻，而两边都以为对上了。只给北京时间更糟——他得自己心算。
  // 时区和北京是同一个墙上时间时只显示一次，不制造噪声。
  if (sameWallClock(dueAtMs, timeZone, BEIJING_ZONE)) {
    return local;
  }
  return `${local}（北京时间 ${relativeLabel(dueAtMs, nowMs, BEIJING_ZONE)}）`;
}

function relativeLabel(dueAtMs, nowMs, timeZone) {
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

// 这个时刻在两个时区里是不是同一个墙上时间。
// 按时区名比的话，重庆的人会看到「14:00（北京时间 14:00）」这种纯噪声。
function sameWallClock(atMs, a, b) {
  if (a === b) {
    return true;
  }
  const pa = ownerParts(atMs, a);
  const pb = ownerParts(atMs, b);
  return pa.year === pb.year && pa.month === pb.month
    && pa.day === pb.day && pa.hour === pb.hour && pa.minute === pb.minute;
}

// UTC 偏移，形如 UTC+11。夏令时重复时段唯一能把两次区分开的东西。
function utcOffsetLabel(atMs, timeZone) {
  const seen = ownerParts(atMs, timeZone);
  const seenAsUtc = Date.UTC(seen.year, seen.month - 1, seen.day, seen.hour, seen.minute, seen.second, 0);
  const minutes = Math.round((seenAsUtc - atMs) / 60000);
  const sign = minutes >= 0 ? "+" : "-";
  const abs = Math.abs(minutes);
  const hh = Math.floor(abs / 60);
  const mm = abs % 60;
  return `UTC${sign}${hh}${mm ? `:${String(mm).padStart(2, "0")}` : ""}`;
}

// 建完立刻回的那一句。不提「已加入队列」「reminder id」这种东西。
function buildConfirmation({ body, dueAtLabel, ambiguous = false, offsetLabel = "" }) {
  const base = body
    ? `好，${dueAtLabel} 提醒你${body}。`
    : `好，${dueAtLabel} 叫你一声。`;
  // 夏令时那天这个点有两次，说清楚是哪一次（AC-016）。不说的话，用户以为的
  // 和实际的差一小时，而两边都觉得自己是对的。
  return ambiguous && offsetLabel
    ? `${base}（那天时钟往回拨，这个点有两次，我按早的那次算，${offsetLabel}。）`
    : base;
}

// 不存在的时刻问的那一句。给出他说的那个点，让他自己挑一个真实存在的。
function buildNonexistentTimeQuestion({ askedFor }) {
  return `那天时钟往前拨，${askedFor} 这个点当天不存在。你是要提前一小时，还是往后挪一小时？`;
}

// 到点发出去的那一句。
function buildDueMessage({ body }) {
  return body ? `到点了，${body}。` : "到点了，你让我这个时候叫你一声。";
}

module.exports = {
  buildConfirmation,
  buildNonexistentTimeQuestion,
  classifyWallClock,
  buildDueMessage,
  extractBody,
  ownerWallClockToMs,
  parseNumber,
  parseReminderIntent,
};
