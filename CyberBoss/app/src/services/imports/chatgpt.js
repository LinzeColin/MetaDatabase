"use strict";

// CB-710 / AC-018: ChatGPT conversations.json. The export stores a message
// tree in `mapping`; nodes are sorted by create_time so the same export always
// yields the same order and therefore the same hash.

const { normalizeConversation } = require("./normalize");

function parseChatGPT(input) {
  const rows = typeof input === "string" ? JSON.parse(input) : input;
  if (!Array.isArray(rows)) {
    throw Object.assign(new Error("IMPORT_FORMAT_UNRECOGNISED"), {
      code: "IMPORT_FORMAT_UNRECOGNISED",
    });
  }
  return rows.map((conversation, conversationIndex) => {
    const mapping = conversation.mapping || {};
    const nodes = Object.values(mapping).filter(
      (node) => node && node.message && node.message.content,
    );
    nodes.sort(
      (left, right) =>
        (left.message.create_time || 0) - (right.message.create_time || 0),
    );
    const messages = nodes.map((node, messageIndex) => {
      const message = node.message;
      const role = message.author && message.author.role;
      const parts = (message.content && message.content.parts) || [];
      return {
        role: role === "assistant" ? "assistant" : role === "user" ? "user" : "system",
        text: parts.filter((part) => typeof part === "string").join("\n"),
        createdAt: message.create_time
          ? new Date(message.create_time * 1000).toISOString()
          : null,
        sourceMessageId: message.id || `${conversationIndex}:${messageIndex}`,
      };
    });
    return normalizeConversation({
      source: "chatgpt",
      sourceConversationId: conversation.id || `chatgpt:${conversationIndex}`,
      title: conversation.title,
      messages,
      compatibility: "stable",
    });
  });
}

module.exports = { parseChatGPT };
