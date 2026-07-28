"use strict";

// CB-730 / AC-037, AC-049: natural Chinese intents mapped to frozen actions.
//
// The mapping is a table lookup, not a model call, so a user's everyday phrasing
// resolves deterministically and a pre-active user can navigate the whole
// product without a single token being spent. Every action name here also
// appears in the portal's frozen allowlist or the WeChat command set — nothing
// routes to an Owner capability.

const CANONICAL = Object.freeze({
  "onboarding.start": ["开始", "我要开始", "怎么开始", "start"],
  "onboarding.consent": ["同意并开始", "我同意", "同意"],
  "onboarding.decline": ["不同意", "拒绝"],
  help: ["帮助", "help", "你能做什么", "怎么用"],
  "portal.home": ["设置", "打开设置", "设置页"],
  "portal.provider": ["连接ai", "连接我的ai", "填密钥", "绑定密钥"],
  "portal.import": ["导入聊天", "导入历史", "导入记录"],
  "portal.profile": ["我的资料", "我的画像", "看看我的资料"],
  "portal.memory": ["我的记忆", "你记得我什么"],
  "portal.revoke": ["退出网页", "退出登录", "关掉网页"],
  "analytics.week": ["最近7天", "最近七天", "这周怎么样"],
  "reminder.create": ["设置提醒", "提醒我"],
  "checkin.disable": ["别再问我", "关闭关心", "停止打扰"],
  "checkin.enable": ["可以问我", "打开关心"],
  "privacy.export": ["导出我的数据", "导出数据"],
  "privacy.delete": ["删除我的数据", "删除我的账号", "注销"],
  "turn.stop": ["停止", "停", "别说了"],
  "usage.remaining": ["还能用多少", "我的额度", "用量"],
});

// Actions an ordinary user may reach. Deliberately disjoint from the
// Owner-only capability set in user-context.js.
const USER_ACTIONS = Object.freeze(Object.keys(CANONICAL));

// Phrasings that must never resolve: an ordinary user asking for an Owner
// capability gets the help text, not a partial match.
const FORBIDDEN_PHRASES = Object.freeze([
  "codex",
  "shell",
  "workspace",
  "sudo",
  "systemctl",
  "root",
  "部署",
  "重启服务器",
]);

const LOOKUP = new Map();
for (const [action, phrases] of Object.entries(CANONICAL)) {
  for (const phrase of phrases) {
    LOOKUP.set(phrase, action);
  }
}

function normalize(text) {
  return String(text === null || text === undefined ? "" : text)
    .trim()
    .toLowerCase()
    // Full-width punctuation and spaces are common on mobile keyboards.
    .replace(/[\s　]+/g, "")
    .replace(/[。，、！？.,!?]+$/g, "");
}

function resolveNoviceCommand(text) {
  const normalized = normalize(text);
  if (!normalized) {
    return null;
  }
  if (FORBIDDEN_PHRASES.some((phrase) => normalized.includes(phrase))) {
    // Never a partial match into an operator surface.
    return null;
  }
  return LOOKUP.get(normalized) || null;
}

module.exports = {
  CANONICAL,
  FORBIDDEN_PHRASES,
  USER_ACTIONS,
  normalize,
  resolveNoviceCommand,
};
