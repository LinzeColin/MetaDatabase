"use strict";

// CB-730 / AC-037, AC-049: every user-facing string the product produces
// without a model. Each entry is Chinese, jargon-free, and — when it reports a
// problem — names exactly one thing the user can do next.

const REPAIR_REQUIRED = Object.freeze([
  "provider_missing",
  "provider_invalid",
  "budget_exhausted",
  "import_too_large",
  "import_unsupported",
  "link_expired",
  "session_expired",
]);

// Words a novice should never have to read in primary copy.
const JARGON = Object.freeze([
  "token", "api", "http", "sql", "sqlite", "json", "csrf", "cookie",
  "endpoint", "payload", "systemd", "shell", "cli", "hmac", "sha256",
  "reservation", "circuit breaker", "webhook",
]);

const MESSAGES = Object.freeze({
  welcome: {
    text: "你好，我是 CyberBoss。回复「开始」我就带你开通。",
    primaryAction: "开始",
  },
  consent: {
    text: "开通前需要你确认：我会保存你发给我的内容，用来为你服务。回复「同意并开始」即可开通。",
    primaryAction: "同意并开始",
  },
  home: {
    text: "已经可以用了。直接和我说话就行；想连接自己的 AI 或导入过去的聊天，回复「设置」。",
    primaryAction: "设置",
  },
  provider_missing: {
    text: "还没连上你自己的 AI。回复「连接我的AI」，我会给你一个只用一次的设置链接。",
    primaryAction: "连接我的AI",
  },
  provider_invalid: {
    // 不说「密钥」：AC-007 要求新手看得到的文案里零技术词。用户不需要知道那
    // 串东西叫什么，他只需要知道现在连不上、以及回哪三个字能修好。
    text: "你自己接的那个 AI 现在连不上了，多半是授权过期了。回复「连接我的AI」重新弄一次就好。",
    primaryAction: "连接我的AI",
  },
  budget_exhausted: {
    text: "今天的 AI 用量已经用完了，明天会自动恢复。想现在继续，可以在设置里调高上限。",
    primaryAction: "设置",
  },
  usage_remaining: {
    text: "今天还剩下大约 {remaining_percent}% 的 AI 用量，用完会自动在明天恢复。",
    primaryAction: null,
  },
  import_too_large: {
    text: "这个文件太大了，我处理不了。可以先在导出时选小一点的范围，再发给我。",
    primaryAction: "导入聊天",
  },
  import_unsupported: {
    text: "这个文件我认不出来。目前支持 ChatGPT、Claude、Gemini 和 DeepSeek 导出的文件。",
    primaryAction: "导入聊天",
  },
  import_partial: {
    text: "导入完成，其中有 {skipped} 条我没读懂，已经跳过，其余都保存好了。",
    primaryAction: "我的资料",
  },
  link_expired: {
    text: "这个链接已经过期了，为了安全每个链接只能用一次。回复「设置」我再给你一个新的。",
    primaryAction: "设置",
  },
  session_expired: {
    text: "网页已经自动退出了，这是为了保护你的资料。回复「设置」重新打开。",
    primaryAction: "设置",
  },
  queue_busy: {
    text: "你上一条我还在处理，等我回复完再发新的就好。",
    primaryAction: null,
  },
  provider_unavailable: {
    text: "AI 服务这会儿不太稳定，我等一下会自动再试一次。",
    primaryAction: null,
  },
  suspended: {
    text: "你的账号已经暂停了，暂时用不了。需要恢复请联系管理员。",
    primaryAction: null,
  },
});

class PresenterError extends Error {
  constructor(code) {
    super(code);
    this.name = "PresenterError";
    this.code = code;
  }
}

function present(key, values = {}) {
  const entry = MESSAGES[key];
  if (!entry) {
    throw new PresenterError("MESSAGE_NOT_DEFINED");
  }
  const text = entry.text.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match,
  );
  return Object.freeze({
    key,
    text,
    primaryAction: entry.primaryAction,
    requiresRepairAction: REPAIR_REQUIRED.includes(key),
  });
}

// Used by the CB-730 suite and validator: no message may leak jargon, and every
// problem message must offer a repair action.
function auditMessages() {
  const problems = [];
  for (const [key, entry] of Object.entries(MESSAGES)) {
    const lowered = entry.text.toLowerCase();
    for (const word of JARGON) {
      if (lowered.includes(word)) {
        problems.push({ key, issue: "jargon", detail: word });
      }
    }
    if (!/[一-龥]/.test(entry.text)) {
      problems.push({ key, issue: "not_chinese" });
    }
    if (REPAIR_REQUIRED.includes(key) && !entry.primaryAction) {
      problems.push({ key, issue: "missing_repair_action" });
    }
  }
  return Object.freeze({
    messageCount: Object.keys(MESSAGES).length,
    problems: Object.freeze(problems),
  });
}

module.exports = { JARGON, MESSAGES, PresenterError, REPAIR_REQUIRED, auditMessages, present };
