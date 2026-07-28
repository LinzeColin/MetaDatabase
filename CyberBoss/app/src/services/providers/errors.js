"use strict";

// CB-700 / AC-017: provider transport failures are normalised into a small set
// of codes with fixed Chinese messages. No provider response body, header or
// credential ever reaches the message, the log or the diagnostic hash.

const { createHash } = require("node:crypto");

const MESSAGES = Object.freeze({
  CREDENTIAL_INVALID: "你的密钥无效或没有权限，请到设置页重新填写。",
  RATE_LIMITED: "请求太频繁了，等一会儿我再帮你试。",
  NO_BALANCE: "这个密钥的额度用完了，请充值或换一个再试。",
  PROVIDER_UNAVAILABLE: "AI 服务暂时不可用，稍后我再帮你试一次。",
  PROVIDER_BAD_RESPONSE: "AI 返回的内容不完整，请再发一次。",
  TIMEOUT: "AI 响应超时了，请再发一次。",
  NETWORK_ERROR: "网络暂时不通，稍后我再帮你试一次。",
});

function normalizeHttpError(providerId, status, body = "") {
  let code = "PROVIDER_UNAVAILABLE";
  if (status === 401 || status === 403) {
    code = "CREDENTIAL_INVALID";
  } else if (status === 429) {
    code = "RATE_LIMITED";
  } else if (status === 402) {
    code = "NO_BALANCE";
  }
  // The diagnostic reflects shape only: provider, status and body length.
  // Hashing the body itself would create a stable correlation handle for user
  // content, so the content is deliberately excluded.
  const diagnosticHash = createHash("sha256")
    .update(`${providerId}:${status}:${Buffer.byteLength(String(body), "utf8")}`)
    .digest("hex");
  return Object.freeze({
    provider: providerId,
    code,
    retryable: status === 429 || status >= 500,
    status,
    message: MESSAGES[code],
    diagnosticHash,
  });
}

function providerError(providerId, code) {
  const error = new Error(code);
  error.code = code;
  error.provider = providerId;
  error.message = MESSAGES[code] || MESSAGES.PROVIDER_UNAVAILABLE;
  return error;
}

module.exports = { MESSAGES, normalizeHttpError, providerError };
