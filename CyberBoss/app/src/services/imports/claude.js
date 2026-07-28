"use strict";

// CB-710 / AC-019: Claude conversations with chat_messages. Content may be a
// string or a block array, so both shapes flatten to text.

const { normalizeConversation } = require("./normalize");

function textFromContent(content) {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((block) => (typeof block === "string" ? block : block && block.text) || "")
      .filter(Boolean)
      .join("\n");
  }
  return (content && content.text) || "";
}

function parseClaude(input) {
  const root = typeof input === "string" ? JSON.parse(input) : input;
  const rows = Array.isArray(root) ? root : root && root.conversations;
  if (!Array.isArray(rows)) {
    throw Object.assign(new Error("IMPORT_FORMAT_UNRECOGNISED"), {
      code: "IMPORT_FORMAT_UNRECOGNISED",
    });
  }
  return rows.map((conversation, conversationIndex) => {
    const list = conversation.chat_messages || conversation.messages || [];
    const messages = list.map((message, messageIndex) => ({
      role:
        message.sender === "assistant" || message.role === "assistant"
          ? "assistant"
          : "user",
      text: textFromContent(message.content || message.text),
      createdAt: message.created_at || message.createdAt || null,
      sourceMessageId:
        message.uuid || message.id || `${conversationIndex}:${messageIndex}`,
    }));
    return normalizeConversation({
      source: "claude",
      sourceConversationId:
        conversation.uuid || conversation.id || `claude:${conversationIndex}`,
      title: conversation.name || conversation.title,
      messages,
      compatibility: "stable",
    });
  });
}

module.exports = { parseClaude, textFromContent };
