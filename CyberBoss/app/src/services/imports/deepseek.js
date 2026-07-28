"use strict";

// CB-710 / AC-021: DeepSeek exports vary between JSON, Markdown and plain
// text. Anything that is not recognisable JSON is preserved verbatim and
// labelled `beta_low_confidence` rather than guessed at.

const { normalizeConversation, stableHash } = require("./normalize");

function looksLikeJson(input) {
  return typeof input !== "string" || /^\s*[[{]/.test(input);
}

function parseDeepSeek(input, { format } = {}) {
  if (format === "markdown" || format === "text" || !looksLikeJson(input)) {
    const text = String(input).trim();
    return [
      normalizeConversation({
        source: "deepseek",
        sourceConversationId: `deepseek-text:${stableHash(text).slice(0, 16)}`,
        title: "DeepSeek 导入内容",
        messages: [{ role: "unknown", text }],
        compatibility: "beta_low_confidence",
      }),
    ];
  }
  const root = typeof input === "string" ? JSON.parse(input) : input;
  const rows = Array.isArray(root)
    ? root
    : (root && (root.conversations || root.chats)) || [root];
  return rows.map((conversation, conversationIndex) => {
    const list = conversation.messages || conversation.chat_messages || [];
    const recognised = list.length > 0;
    const messages = list.map((message, messageIndex) => ({
      role:
        message.role === "assistant"
          ? "assistant"
          : message.role === "user"
            ? "user"
            : "unknown",
      text: message.content || message.text || "",
      createdAt: message.created_at || message.createdAt || null,
      sourceMessageId: message.id || `${conversationIndex}:${messageIndex}`,
    }));
    return normalizeConversation({
      source: "deepseek",
      sourceConversationId: conversation.id || `deepseek:${conversationIndex}`,
      title: conversation.title || "DeepSeek 对话",
      messages,
      compatibility: recognised ? "beta" : "beta_low_confidence",
    });
  });
}

module.exports = { looksLikeJson, parseDeepSeek };
