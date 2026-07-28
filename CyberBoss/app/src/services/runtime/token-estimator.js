"use strict";

// CB-700 / AC-045: a conservative upper bound on input tokens, computed before
// the provider is called. A byte-level tokenizer cannot emit more content
// tokens than the UTF-8 byte sequence, so this over-reserves on purpose; the
// provider's reported usage later settles the reservation down to actual use.

class TokenEstimatorError extends Error {
  constructor(code) {
    super(code);
    this.name = "TokenEstimatorError";
    this.code = code;
  }
}

const PER_MESSAGE_OVERHEAD = 16;
const ENVELOPE_OVERHEAD = 32;

function stringifyContent(content) {
  if (typeof content === "string") {
    return content;
  }
  if (content === null || content === undefined) {
    return "";
  }
  return JSON.stringify(content);
}

function estimateInputTokenUpperBound(messages) {
  if (!Array.isArray(messages)) {
    throw new TokenEstimatorError("MESSAGES_MUST_BE_ARRAY");
  }
  let utf8Bytes = 0;
  for (const message of messages) {
    if (!message || typeof message !== "object") {
      throw new TokenEstimatorError("MESSAGE_INVALID");
    }
    utf8Bytes += Buffer.byteLength(String(message.role || ""), "utf8");
    utf8Bytes += Buffer.byteLength(stringifyContent(message.content), "utf8");
    utf8Bytes += PER_MESSAGE_OVERHEAD;
  }
  return Math.max(1, utf8Bytes + ENVELOPE_OVERHEAD);
}

module.exports = {
  ENVELOPE_OVERHEAD,
  PER_MESSAGE_OVERHEAD,
  TokenEstimatorError,
  estimateInputTokenUpperBound,
};
