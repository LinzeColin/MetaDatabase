"use strict";

// CB-740 / AC-043: proactive check-ins are entirely deterministic.
//
// Whether to speak, when to speak and which words to use are all decided by
// arithmetic and a frozen template table. The module imports nothing, so a
// background check-in cannot consume a model token even by accident, and a user
// who turns it off receives exactly zero proactive messages.

const TEMPLATES = Object.freeze({
  morning: "早上好。今天有什么想先处理的吗？",
  evening: "今天过得怎么样？想说点什么我都在。",
  idle: "有一阵子没聊了，一切都还好吗？",
  reminder_due: "到点啦：{title}",
  streak: "你已经连续记录 {days} 天了，挺好的。",
});

const SLOTS = Object.freeze(["morning", "evening", "idle"]);
const DEFAULT_QUIET_HOURS = Object.freeze({ start: 22, end: 8 });
const DEFAULT_MIN_INTERVAL_MS = 12 * 60 * 60 * 1000;

class CheckinError extends Error {
  constructor(code) {
    super(code);
    this.name = "CheckinError";
    this.code = code;
  }
}

function hourInZone(epochMs, offsetMinutes) {
  const shifted = new Date(epochMs + offsetMinutes * 60_000);
  if (!Number.isFinite(shifted.getTime())) {
    throw new CheckinError("CLOCK_INVALID");
  }
  return shifted.getUTCHours();
}

// Handles the wrap-around case (22:00 to 08:00) as well as a same-day window.
function inQuietHours(hour, quietHours) {
  const { start, end } = quietHours;
  return start <= end ? hour >= start && hour < end : hour >= start || hour < end;
}

function renderTemplate(slot, values = {}) {
  const template = TEMPLATES[slot];
  if (!template) {
    throw new CheckinError("CHECKIN_TEMPLATE_UNKNOWN");
  }
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match,
  );
}

// The single decision function. Returns modelCalls: 0 on every path, including
// the path that decides to send.
function decideCheckin({
  enabled,
  nowMs,
  lastCheckinMs = null,
  timezoneOffsetMinutes = 480,
  quietHours = DEFAULT_QUIET_HOURS,
  minIntervalMs = DEFAULT_MIN_INTERVAL_MS,
  values = {},
}) {
  if (!enabled) {
    return Object.freeze({ send: false, reason: "disabled_by_user", modelCalls: 0 });
  }
  const hour = hourInZone(nowMs, timezoneOffsetMinutes);
  if (inQuietHours(hour, quietHours)) {
    return Object.freeze({ send: false, reason: "quiet_hours", modelCalls: 0, hour });
  }
  if (lastCheckinMs !== null && nowMs - lastCheckinMs < minIntervalMs) {
    return Object.freeze({ send: false, reason: "too_soon", modelCalls: 0 });
  }
  // Slot selection is a pure function of the local hour.
  const slot = hour < 12 ? "morning" : hour < 20 ? "evening" : "idle";
  return Object.freeze({
    send: true,
    reason: "scheduled",
    slot,
    text: renderTemplate(slot, values),
    modelCalls: 0,
  });
}

module.exports = {
  CheckinError,
  DEFAULT_MIN_INTERVAL_MS,
  DEFAULT_QUIET_HOURS,
  SLOTS,
  TEMPLATES,
  decideCheckin,
  inQuietHours,
  renderTemplate,
};
