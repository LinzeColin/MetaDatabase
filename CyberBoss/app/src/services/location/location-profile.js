"use strict";

// 多信号合并、置信度与那一句中文确认（CB9-220 / AC-013、AC-014）。
//
// AC-014 的原话：「显式陈述优先于浏览器，浏览器优先于 Cloudflare；冲突低置信时
// 只在首条成功回复后提一次中文确认。」拆开是四件独立的事，任何一件写错的表现
// 都不一样：
//
//   优先级错   → 用 VPN 的人被按出口 IP 的时区安排提醒。
//   置信度错   → 该问的不问，或者不该问的乱问。
//   「首条之后」错 → 人还没见到第一句回复，先被问了个莫名其妙的问题。
//   「只一次」错  → 每句话后面都跟一句「你是不是在悉尼？」——比不问更烦人。
//
// 所以这四件分别有自己的判定函数和自己的测试，不揉成一个大 if。
//
// 隐私（AC-013）在这一层是**结构性**的：能落库的字段由 016/017 的表结构决定，
// 那里根本没有 raw_ip / latitude / longitude 三列。这个模块只保证不往回传——
// 任何要出库进 Timeline/Status/日志的东西都走 publicProjection()。

const { BEIJING_ZONE, formatInZone, normalizeUserZone } = require("../time/canonical-time");
const {
  SIGNAL_PRIORITY,
  assertNoPreciseLocation,
  defaultConfidence,
} = require("./timezone-signals");

// 低于这个值就要问。0.4 是 Cloudflare 的默认置信度——也就是说「只有 Cloudflare
// 说话」永远会触发确认，而浏览器（0.8）单独说话不会。
const CONFIRM_BELOW_CONFIDENCE = 0.6;

// 两个信号都在但对不上，就算各自置信度都不低，也要问。
// 一个人的设备说悉尼、出口 IP 说奥克兰，猜错的代价是提醒差两小时。
const CONFLICT_PENALTY = 0.3;

function normalizeSignal(signal) {
  if (!signal || typeof signal !== "object") {
    return null;
  }
  const source = String(signal.source || "");
  if (!(source in SIGNAL_PRIORITY)) {
    return null;
  }
  const timezone = String(signal.timezone || "");
  if (!timezone) {
    return null;
  }
  return {
    source,
    timezone,
    city: signal.city ?? null,
    country: signal.country ?? null,
    confidence: Number.isFinite(signal.confidence) ? signal.confidence : defaultConfidence(source),
    observed_at_utc: signal.observed_at_utc || null,
  };
}

// 两个时区是不是「同一件事」。
//
// 按字符串比的话，Asia/Shanghai 和 Asia/Chongqing 会被判成冲突，于是一个在重庆
// 的人会被问「你到底在上海还是重庆」——两个答案对他来说毫无区别。按**当下渲染
// 出来的墙上时间**比才是用户能感知的那个差别。
function sameWallClock(a, b, at = new Date()) {
  if (a === b) {
    return true;
  }
  try {
    return formatInZone(at, normalizeUserZone(a), { seconds: false })
      === formatInZone(at, normalizeUserZone(b), { seconds: false });
  } catch {
    return false;
  }
}

// 按冻结优先级合并。
//
// 返回 winner + 是否冲突 + 合并后的置信度。**不做**「该不该问」的判断——那要看
// 库里问没问过，是另一件事，在 shouldAskConfirmation 里。
function mergeLocationSignals(signals = [], { at = new Date() } = {}) {
  const clean = (Array.isArray(signals) ? signals : [])
    .map(normalizeSignal)
    .filter(Boolean);
  if (!clean.length) {
    return Object.freeze({
      timezone: BEIJING_ZONE,
      source: null,
      confidence: 0,
      conflict: false,
      // 一个信号都没有时不是「猜北京」，是「按默认口径办」。两者对用户是同一
      // 个结果，但对「要不要问他」是相反的：没信号不该问——问了他也答不出个
      // 所以然，而且这是绝大多数人的默认状态。
      fallback: true,
      city: null,
      country: null,
    });
  }
  // 优先级小的赢；同优先级的按观测时间新的赢。
  const sorted = [...clean].sort((a, b) => {
    const byPriority = SIGNAL_PRIORITY[a.source] - SIGNAL_PRIORITY[b.source];
    if (byPriority !== 0) {
      return byPriority;
    }
    return String(b.observed_at_utc || "").localeCompare(String(a.observed_at_utc || ""));
  });
  const winner = sorted[0];
  // 冲突只看**别的信号源**里有没有和赢家墙上时间不一样的。
  const conflict = sorted.slice(1).some(
    (other) => other.source !== winner.source && !sameWallClock(other.timezone, winner.timezone, at),
  );
  const confidence = Math.max(0, Math.min(1,
    winner.confidence - (conflict ? CONFLICT_PENALTY : 0)));
  return Object.freeze({
    timezone: winner.timezone,
    source: winner.source,
    confidence,
    conflict,
    fallback: false,
    // 城市国家跟着赢家走。赢家没有就往下找一个有的——它们是粗粒度的补充信息，
    // 不参与时区判断，所以借用别的信号源的不会造成时间错乱。
    city: winner.city ?? sorted.find((s) => s.city)?.city ?? null,
    country: winner.country ?? sorted.find((s) => s.country)?.country ?? null,
  });
}

// 该不该问那一句。四个条件全部成立才问。
function shouldAskConfirmation({
  merged,
  profile = null,
  firstReplyDelivered = false,
} = {}) {
  // 一、首条成功回复之前不问。人还没见到第一句话就被问问题，是最差的第一印象。
  if (!firstReplyDelivered) {
    return false;
  }
  // 二、用户自己说过的不问。他说了就是了。
  if (merged?.source === "explicit_user" || profile?.confirmed) {
    return false;
  }
  // 三、一个信号都没有的不问。这是绝大多数人的默认状态，问了他也答不出所以然。
  if (!merged || merged.fallback) {
    return false;
  }
  // 四、置信度够高且不冲突的不问。
  if (!merged.conflict && merged.confidence >= CONFIRM_BELOW_CONFIDENCE) {
    return false;
  }
  // 五、问过一次就不再问——除非这次要问的时区和上次问的**不是同一件事**。
  //     换了个地方是新情况，值得再问一次；同一个地方问第二遍就是骚扰。
  const asked = profile?.confirmation_asked_at_utc;
  if (asked) {
    const askedZone = profile?.confirmation_asked_timezone || "";
    if (!askedZone || sameWallClock(askedZone, merged.timezone)) {
      return false;
    }
  }
  return true;
}

// 那句中文。一句话、给个默认、不留作业。
//
// 不写成「请回复 1 确认 / 2 取消」：这是微信聊天，不是 IVR。用户会用大白话回
// 「对」「不是，我在东京」，那两种都由模型和 CB9-240 的自然语言纠正接住。
function buildConfirmationQuestion(merged) {
  const zone = merged?.timezone || BEIJING_ZONE;
  const place = merged?.city || zoneTail(zone);
  return `顺便问一句——你现在是在${place}吗？我按这个给你算时间。不对的话直接告诉我你在哪儿就行。`;
}

function zoneTail(zone) {
  const tail = String(zone || "").split("/").pop() || "";
  return tail.replace(/_/g, " ") || "那边";
}

// 出库投影：能进 Timeline / Status / 日志 / 备份 payload 的字段白名单。
//
// AC-013 扫的是这五个地方。库里没有精确字段是第一道防线（结构性），这是第二道
// ——万一以后有人往表上加了列，白名单不会自动把它放出去。
const PUBLIC_FIELDS = Object.freeze(["timezone", "coarse_city", "coarse_country", "source", "confidence", "confirmed"]);

function publicProjection(profile) {
  if (!profile) {
    return null;
  }
  // 先 fail-closed：投影的输入本身就不该含精确字段。
  assertNoPreciseLocation(profile);
  const out = {};
  for (const field of PUBLIC_FIELDS) {
    if (profile[field] !== undefined) {
      out[field] = profile[field];
    }
  }
  return Object.freeze(out);
}

module.exports = {
  CONFIRM_BELOW_CONFIDENCE,
  CONFLICT_PENALTY,
  PUBLIC_FIELDS,
  buildConfirmationQuestion,
  mergeLocationSignals,
  publicProjection,
  sameWallClock,
  shouldAskConfirmation,
};
