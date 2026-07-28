"use strict";

// CB-710: the only entry point that turns an uploaded file into canonical
// records. A corrupt conversation is quarantined rather than aborting the
// whole import, so one bad row cannot cost a user their entire history.

const { parseChatGPT } = require("./chatgpt");
const { parseClaude } = require("./claude");
const { parseDeepSeek } = require("./deepseek");
const { parseGemini } = require("./gemini");

const SOURCES = Object.freeze(["chatgpt", "claude", "gemini", "deepseek"]);
const STABLE_SOURCES = Object.freeze(["chatgpt", "claude"]);

class ImportRouterError extends Error {
  constructor(code) {
    super(code);
    this.name = "ImportRouterError";
    this.code = code;
  }
}

function parseImport({ source, input, format }) {
  switch (source) {
    case "chatgpt":
      return parseChatGPT(input);
    case "claude":
      return parseClaude(input);
    case "gemini":
      return parseGemini(input, { format });
    case "deepseek":
      return parseDeepSeek(input, { format });
    default:
      throw new ImportRouterError("IMPORT_SOURCE_UNSUPPORTED");
  }
}

// Parses each conversation independently so a single malformed record is
// isolated with a reason instead of failing the batch.
function parseImportIsolating({ source, input, format }) {
  if (!SOURCES.includes(source)) {
    throw new ImportRouterError("IMPORT_SOURCE_UNSUPPORTED");
  }
  let rows;
  try {
    rows = typeof input === "string" && /^\s*[[{]/.test(input) ? JSON.parse(input) : input;
  } catch {
    throw new ImportRouterError("IMPORT_FORMAT_UNRECOGNISED");
  }
  const list = Array.isArray(rows)
    ? rows
    : (rows && (rows.conversations || rows.chats || rows.items)) || null;
  if (!Array.isArray(list)) {
    // Not a per-conversation structure: parse whole and let the source parser
    // decide its own compatibility label.
    return Object.freeze({
      conversations: parseImport({ source, input, format }),
      quarantined: Object.freeze([]),
    });
  }
  const conversations = [];
  const quarantined = [];
  list.forEach((conversation, index) => {
    let parsed;
    try {
      parsed = parseImport({ source, input: [conversation], format });
    } catch (error) {
      // The reason is a code, never the record's content.
      quarantined.push(Object.freeze({ index, reason: error.code || "PARSE_FAILED" }));
      return;
    }
    // A record whose structure survived JSON but yielded nothing readable is
    // corrupt in the way that matters: it would import as an empty shell and
    // silently look like a successful import of nothing.
    const usable = parsed.filter((record) => record.messages.length > 0);
    if (usable.length === 0) {
      quarantined.push(Object.freeze({ index, reason: "NO_PARSEABLE_MESSAGES" }));
      return;
    }
    conversations.push(...usable);
  });
  return Object.freeze({
    conversations: Object.freeze(conversations),
    quarantined: Object.freeze(quarantined),
  });
}

module.exports = {
  ImportRouterError,
  SOURCES,
  STABLE_SOURCES,
  parseImport,
  parseImportIsolating,
};
