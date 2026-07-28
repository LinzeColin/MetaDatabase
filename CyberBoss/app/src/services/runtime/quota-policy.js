"use strict";

// CB-630 / AC-044: admission limits with deterministic Chinese degradation.
// Every refusal is a fixed string chosen by a table lookup — no model call is
// involved in deciding or wording a limit, and one user hitting a limit never
// changes another user's outcome.

const LIMITS = Object.freeze({
  perUserActive: 1,
  perUserQueued: 3,
  globalProviderActive: 2,
  globalImportActive: 1,
  maxTextBytes: 32 * 1024,
});

const KINDS = Object.freeze(["ai", "import", "command"]);

// Frozen copy. Each entry names the situation and the one thing to do next.
const REFUSALS = Object.freeze({
  TEXT_TOO_LARGE: "这条消息太长了，请分成几条发给我。",
  USER_ACTIVE_BUSY: "你上一条还在处理中，等我回复后再发新的就好。",
  USER_QUEUE_FULL: "你已经有几条在排队了，等我回复后再发新的就好。",
  GLOBAL_PROVIDER_BUSY: "现在使用的人比较多，你的这条已经安全排队，我会尽快处理。",
  IMPORT_BUSY: "已经有一个导入在进行，你的文件会排在后面自动开始。",
});

function evaluateQuota({
  kind,
  text = "",
  userActive = 0,
  userQueued = 0,
  globalProviderActive = 0,
  globalImportActive = 0,
  limits = LIMITS,
}) {
  if (!KINDS.includes(kind)) {
    return refuse("KIND_INVALID", "这个操作我暂时不支持，回复「帮助」看看能做什么。");
  }
  const effective = { ...LIMITS, ...limits };

  if (Buffer.byteLength(String(text), "utf8") > effective.maxTextBytes) {
    return refuse("TEXT_TOO_LARGE", REFUSALS.TEXT_TOO_LARGE);
  }

  if (kind === "ai") {
    if (userActive >= effective.perUserActive) {
      return refuse("USER_ACTIVE_BUSY", REFUSALS.USER_ACTIVE_BUSY);
    }
    if (userQueued >= effective.perUserQueued) {
      return refuse("USER_QUEUE_FULL", REFUSALS.USER_QUEUE_FULL);
    }
    if (globalProviderActive >= effective.globalProviderActive) {
      return refuse("GLOBAL_PROVIDER_BUSY", REFUSALS.GLOBAL_PROVIDER_BUSY);
    }
  }

  if (kind === "import" && globalImportActive >= effective.globalImportActive) {
    return refuse("IMPORT_BUSY", REFUSALS.IMPORT_BUSY);
  }

  return Object.freeze({ allowed: true, code: "OK", message: null, modelCalls: 0 });
}

function refuse(code, message) {
  return Object.freeze({ allowed: false, code, message, modelCalls: 0 });
}

module.exports = { KINDS, LIMITS, REFUSALS, evaluateQuota };
