"use strict";

// CB-710 / AC-020: Gemini has no single stable export contract, so this parser
// is honest about what it recognised. A JSON export it understands is labelled
// `beta`; an HTML page it can only strip to text is labelled
// `beta_low_confidence`. An unknown structure is never presented as complete.

const { normalizeConversation, stableHash } = require("./normalize");

function stripHtml(html) {
  return String(html)
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function looksLikeHtml(input) {
  return typeof input === "string" && /^\s*</.test(input);
}

function parseGemini(input, { format } = {}) {
  if (format === "html" || looksLikeHtml(input)) {
    const text = stripHtml(input);
    return [
      normalizeConversation({
        source: "gemini",
        sourceConversationId: `gemini-html:${stableHash(text).slice(0, 16)}`,
        title: "Gemini 导入内容",
        messages: [{ role: "unknown", text }],
        compatibility: "beta_low_confidence",
      }),
    ];
  }
  const root = typeof input === "string" ? JSON.parse(input) : input;
  const rows = Array.isArray(root)
    ? root
    : (root && (root.conversations || root.items)) || [root];
  return rows.map((conversation, conversationIndex) => {
    const list =
      conversation.messages || conversation.turns || conversation.entries || [];
    const recognised = list.length > 0;
    const messages = list.map((message, messageIndex) => ({
      role:
        message.role === "model" || message.role === "assistant"
          ? "assistant"
          : message.role === "user"
            ? "user"
            : "unknown",
      text: message.text || message.content || message.prompt || message.response || "",
      createdAt: message.createdAt || message.timestamp || null,
      sourceMessageId: message.id || `${conversationIndex}:${messageIndex}`,
    }));
    return normalizeConversation({
      source: "gemini",
      sourceConversationId: conversation.id || `gemini:${conversationIndex}`,
      title: conversation.title || "Gemini 对话",
      messages,
      // No recognisable message list means the confidence must drop, not the
      // label stay optimistic.
      compatibility: recognised ? "beta" : "beta_low_confidence",
    });
  });
}

module.exports = { looksLikeHtml, parseGemini, stripHtml };
