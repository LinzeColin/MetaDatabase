"use strict";

// 时区信号采集（CB9-210 / AC-012、AC-042、AC-013 的入口面）。
//
// FR-012 的原话是「加入页**静默**采集浏览器 IANA 时区」。静默这两个字决定了整
// 个设计：
//
//   Intl.DateTimeFormat().resolvedOptions().timeZone 不需要任何权限，也不会弹
//   任何框。navigator.geolocation 需要权限、会弹框，而且拿到的是经纬度——一个
//   我们**根本不打算存**的东西（016 迁移里压根没有那两列）。
//
// 所以这条路上一次都不问位置权限。AC-042 要的是「拒绝定位权限后仍能完成扫码和
// 首轮，且不重复弹窗」——一次都不弹是它的严格超集，而且不给自己留一条以后有人
// 「顺手加个精确定位」的口子。加入页里出现 geolocation 就转红，有测试守着。
//
// 三个信号源，优先级是冻结的：
//   explicit_user       —— 用户自己说的（「我在悉尼」）。人比推断准。
//   browser_iana        —— 浏览器报的 IANA 时区。设备自己的设置，通常就是对的。
//   cloudflare_timezone —— 只作佐证。它是按出口 IP 猜的，用 VPN 的人会被猜错，
//                          所以永远不能盖过前两个。
//
// 隐私是 fail-closed 的：任何一个精确定位/网络标识字段出现在要落库的观测里，
// 直接抛错，而不是「悄悄挑出安全字段」。悄悄丢弃会把上游的隐私回归藏起来——
// 那一版代码依然在把经纬度传进来，只是没人看见。

const { BEIJING_ZONE, isValidIanaZone, normalizeUserZone } = require("../time/canonical-time");

// 冻结优先级。数字小的赢。
const SIGNAL_PRIORITY = Object.freeze({
  explicit_user: 0,
  browser_iana: 1,
  cloudflare_timezone: 2,
});
const KNOWN_SOURCES = Object.freeze(Object.keys(SIGNAL_PRIORITY));

// 这些字段一旦出现在长期观测里就是 AC-013 的违规。
const FORBIDDEN_FIELDS = Object.freeze(new Set([
  "ip", "raw_ip", "client_ip", "remote_addr", "connecting_ip", "forwarded_for",
  "latitude", "longitude", "lat", "lng", "lon", "coords", "coordinates",
  "accuracy", "altitude", "heading", "speed", "geohash",
  "street", "street_address", "address", "postal_code", "postcode", "zip",
]));

// 粗粒度字段的长度上限。城市名再长也不会到 64；超了说明塞进来的不是城市。
const MAX_COARSE_LENGTH = 64;

function normalizeKey(key) {
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

// 递归查禁用字段。深层嵌套里藏一个 coords 也要抓出来。
function assertNoPreciseLocation(value, path = "$", seen = new WeakSet()) {
  if (!value || typeof value !== "object") {
    return;
  }
  if (seen.has(value)) {
    return;
  }
  seen.add(value);
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_FIELDS.has(normalizeKey(key))) {
      throw new Error(`forbidden precise location field at ${path}.${key}`);
    }
    assertNoPreciseLocation(child, `${path}.${key}`, seen);
  }
}

function coarseText(value) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > MAX_COARSE_LENGTH) {
    return null;
  }
  // 只收字母、数字、空格和常见连接符。Cloudflare 的头是可以被上游改的，进来的
  // 东西会被写进库、进 Timeline、再进模型上下文——挡一道注入面。
  return /^[\p{L}\p{N} .'\-_]+$/u.test(trimmed) ? trimmed : null;
}

// Cloudflare 头里只取这三个，且都是粗粒度的。
//
// **不读** cf-connecting-ip / x-forwarded-for / x-real-ip。这不是疏忽——原始 IP
// 是 AC-013 明令不许落库的东西，而最安全的处理是从来不把它读进变量里：读不到
// 就不会有人在下一次改动里「顺手」把它传下去。
function readCloudflareSignals(headers = {}) {
  const get = (name) => {
    const raw = headers?.[name] ?? headers?.[name.toUpperCase()];
    return Array.isArray(raw) ? raw[0] : raw;
  };
  // 时区**不走** coarseText。那个正则是给城市名的，不含斜杠，会把
  // Asia/Shanghai 整个拒掉。时区的校验器是 isValidIanaZone——它比任何正则都
  // 严格，因为它真的让 Intl 去解析一遍。
  const timezone = get("cf-timezone");
  const country = coarseText(get("cf-ipcountry"));
  const city = coarseText(get("cf-ipcity"));
  return Object.freeze({
    // 时区认不出来就当没有，不回退——回退是合并层（CB9-220）的事，采集层只负责
    // 如实说「我这里有/没有」。
    timezone: isValidIanaZone(typeof timezone === "string" ? timezone.trim() : timezone)
      ? timezone.trim()
      : null,
    // XX 是 Cloudflare 对「不知道」的编码，T1 是 Tor 出口。都不算国家。
    country: country && country !== "XX" && country !== "T1" ? country.toUpperCase() : null,
    city: city || null,
  });
}

// 浏览器上报。拿不到就是 null，不猜。
function normalizeBrowserTimezone(value) {
  const zone = typeof value === "string" ? value.trim() : "";
  return isValidIanaZone(zone) ? zone : null;
}

// 组装一条**可以落库**的观测。任何精确定位字段都会让它抛错。
function safeObservation(raw = {}) {
  // 检查**原始入参**，不是解构出来的那几个字段。
  //
  // 第一版我写的是 assertNoPreciseLocation({source, timezone, city, country, ...})
  // ——用解构出来的对象去查。那样的话调用方传进来的 latitude 根本没进被检查的
  // 那个对象，整道 fail-closed 检查形同虚设，而且**任何**只传合法字段的测试都
  // 是绿的。这正是这个仓的招牌坏法：中间层按名字解构，多出来的字段被静默丢掉。
  // 写隐私守卫的时候踩进去尤其贵：守卫在，但守的是空气。
  assertNoPreciseLocation(raw);
  const {
    source,
    timezone,
    city = null,
    country = null,
    confidence,
    consentScope = "timezone_only",
    observedAtUtc,
  } = raw;
  if (!KNOWN_SOURCES.includes(source)) {
    throw new RangeError(`unknown timezone signal source: ${String(source)}`);
  }
  if (!isValidIanaZone(timezone)) {
    throw new RangeError("observation requires a valid IANA timezone");
  }
  const score = Number.isFinite(confidence)
    ? Math.min(1, Math.max(0, confidence))
    : defaultConfidence(source);
  return Object.freeze({
    source,
    timezone,
    city: coarseText(city),
    country: coarseText(country),
    confidence: score,
    consent_scope: String(consentScope || "timezone_only"),
    observed_at_utc: observedAtUtc || new Date().toISOString(),
  });
}

// 默认置信度跟着来源走。用户自己说的最高；Cloudflare 是按出口 IP 猜的，用 VPN
// 的人会被猜错，所以给得低——低到会触发 CB9-220 的那句中文确认。
function defaultConfidence(source) {
  if (source === "explicit_user") return 1;
  if (source === "browser_iana") return 0.8;
  return 0.4;
}

// 扫码那一刻还不知道来的是谁——用户是扫完之后才存在的。所以观测先按 ticket
// 暂存，等身份出来再绑（绑定和合并在 CB9-220）。
//
// 这个暂存必须有 TTL 和上限：它挂在一个**无鉴权**的公开接口后面，没有上限就是
// 一个人人可写的内存增长点。
class PendingTimezoneSignals {
  constructor({ ttlMs = 10 * 60 * 1000, maxEntries = 200 } = {}) {
    this.ttlMs = ttlMs;
    this.maxEntries = maxEntries;
    this.entries = new Map();
  }

  prune(now = Date.now()) {
    for (const [ticket, entry] of this.entries) {
      if (now - entry.at > this.ttlMs) {
        this.entries.delete(ticket);
      }
    }
    // 还是超了就丢最旧的。Map 保持插入序，先进的在前面。
    while (this.entries.size > this.maxEntries) {
      const oldest = this.entries.keys().next();
      if (oldest.done) break;
      this.entries.delete(oldest.value);
    }
  }

  record(ticket, observation, { now = Date.now() } = {}) {
    const key = typeof ticket === "string" ? ticket.trim() : "";
    if (!key || !observation) {
      return false;
    }
    this.prune(now);
    // 同一张票重复上报：留**优先级更高**的那个，不是留最后一个。
    // 留最后一个的话，页面里晚一点触发的 Cloudflare 佐证会盖掉浏览器的上报。
    const existing = this.entries.get(key);
    if (existing && SIGNAL_PRIORITY[existing.observation.source] <= SIGNAL_PRIORITY[observation.source]) {
      return false;
    }
    this.entries.set(key, { at: now, observation });
    // 插入**之后**再裁一次。只在插入前 prune 的话，每次都会停在
    // maxEntries + 1 上——差一，但差的那一条是一个无鉴权接口写进来的。
    this.prune(now);
    return true;
  }

  take(ticket, { now = Date.now() } = {}) {
    const key = typeof ticket === "string" ? ticket.trim() : "";
    if (!key) {
      return null;
    }
    this.prune(now);
    const entry = this.entries.get(key);
    if (!entry) {
      return null;
    }
    this.entries.delete(key);
    return entry.observation;
  }

  get size() {
    return this.entries.size;
  }
}

module.exports = {
  BEIJING_ZONE,
  FORBIDDEN_FIELDS,
  KNOWN_SOURCES,
  MAX_COARSE_LENGTH,
  PendingTimezoneSignals,
  SIGNAL_PRIORITY,
  assertNoPreciseLocation,
  coarseText,
  defaultConfidence,
  normalizeBrowserTimezone,
  normalizeKey,
  normalizeUserZone,
  readCloudflareSignals,
  safeObservation,
};
