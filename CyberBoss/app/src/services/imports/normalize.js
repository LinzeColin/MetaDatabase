"use strict";

// CB-710 / AC-018..AC-021: every source parses into one canonical conversation
// shape whose hash is stable under key ordering, so re-importing the same
// export produces the same identity and therefore no duplicate facts.

const { createHash } = require("node:crypto");

const ROLES = Object.freeze(["user", "assistant", "system"]);
const COMPATIBILITY = Object.freeze(["stable", "beta", "beta_low_confidence"]);
const MAX_TITLE_LENGTH = 200;

function canonical(value) {
  if (Array.isArray(value)) {
    return value.map(canonical);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonical(value[key])]),
    );
  }
  return value;
}

function stableHash(value) {
  return createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex");
}

function normalizeConversation({
  source,
  sourceConversationId,
  title,
  messages,
  compatibility = "stable",
}) {
  if (!COMPATIBILITY.includes(compatibility)) {
    throw new TypeError("unknown compatibility label");
  }
  const clean = (messages || [])
    .map((message, index) => ({
      role: ROLES.includes(message.role) ? message.role : "unknown",
      text: String(message.text || "").trim(),
      createdAt: message.createdAt || null,
      sourceMessageId:
        message.sourceMessageId || `${sourceConversationId || "conv"}:${index}`,
    }))
    .filter((message) => message.text);
  const record = {
    source,
    sourceConversationId: String(
      sourceConversationId || stableHash(clean).slice(0, 20),
    ),
    title: String(title || "未命名对话").slice(0, MAX_TITLE_LENGTH),
    compatibility,
    messages: clean,
  };
  return Object.freeze({ ...record, sourceHash: stableHash(record) });
}

module.exports = { COMPATIBILITY, ROLES, canonical, normalizeConversation, stableHash };
