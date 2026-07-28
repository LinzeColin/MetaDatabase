"use strict";

// CB-620 / AC-004: the WeChat onboarding reducer. It is a pure state machine —
// every transition is decided by string equality and stored status, so the
// number of model calls before a user is active is structurally zero.

const COMMANDS = Object.freeze({
  START: "开始",
  CONSENT: "同意并开始",
  DECLINE: "不同意",
  CANCEL: "退出",
});

const STATES = Object.freeze([
  "unseen",
  "pending_invite",
  "pending_consent",
  "active",
  "suspended",
]);

const ACTIONS = Object.freeze({
  REQUEST_INVITE: "request_invite_code",
  SHOW_CONSENT: "show_consent",
  SHOW_HOME: "show_home",
  CONSENT_DECLINED: "consent_declined",
  CANCELLED: "cancelled",
  PROMPT_REQUIRED_STEP: "prompt_required_step",
  ROUTE_ACTIVE_USER: "route_active_user",
  SUSPENDED: "suspended_notice",
});

// Chinese copy for every pre-active state; none of it is model-generated.
const MESSAGES = Object.freeze({
  [ACTIONS.REQUEST_INVITE]:
    "你好，这里是 CyberBoss。请把邀请码发给我，我就帮你开通。",
  [ACTIONS.SHOW_CONSENT]:
    "开通前需要你确认：我会保存你发给我的内容，用来提供服务。回复「同意并开始」即可开通，回复「不同意」就到此为止。",
  [ACTIONS.SHOW_HOME]:
    "已开通。你可以直接和我说话；回复「设置」打开设置页面，回复「退出」随时停用。",
  [ACTIONS.CONSENT_DECLINED]:
    "已停止开通，你的资料不会被使用。想重新开始时回复「开始」。",
  [ACTIONS.CANCELLED]: "已取消。想重新开始时回复「开始」。",
  [ACTIONS.PROMPT_REQUIRED_STEP]:
    "还差一步才能开通。请按上一条提示回复，或回复「退出」取消。",
  [ACTIONS.SUSPENDED]:
    "你的账号已暂停，暂时无法使用。需要恢复时请联系管理员。",
});

// A pre-active turn may never reach a provider. `modelCalls: 0` is asserted by
// the CB-620 suite for every transition this reducer can produce.
function reduceOnboarding(state, text, { inviteValidated = false } = {}) {
  const current = STATES.includes(state) ? state : "unseen";
  const input = String(text === null || text === undefined ? "" : text).trim();

  if (current === "suspended") {
    return frozen("suspended", ACTIONS.SUSPENDED, 0);
  }
  if (current === "unseen") {
    return input === COMMANDS.START
      ? frozen("pending_invite", ACTIONS.REQUEST_INVITE, 0)
      : frozen("unseen", ACTIONS.PROMPT_REQUIRED_STEP, 0);
  }
  if (current === "pending_invite") {
    if (input === COMMANDS.CANCEL) {
      return frozen("unseen", ACTIONS.CANCELLED, 0);
    }
    return inviteValidated
      ? frozen("pending_consent", ACTIONS.SHOW_CONSENT, 0)
      : frozen("pending_invite", ACTIONS.REQUEST_INVITE, 0);
  }
  if (current === "pending_consent") {
    if (input === COMMANDS.CONSENT) {
      return frozen("active", ACTIONS.SHOW_HOME, 0);
    }
    if (input === COMMANDS.DECLINE) {
      return frozen("pending_consent", ACTIONS.CONSENT_DECLINED, 0);
    }
    if (input === COMMANDS.CANCEL) {
      return frozen("unseen", ACTIONS.CANCELLED, 0);
    }
    return frozen("pending_consent", ACTIONS.PROMPT_REQUIRED_STEP, 0);
  }
  // Only an active user reaches a turn that may consume model tokens; the
  // budget and circuit decision itself lives in the CB-700 controller.
  return frozen("active", ACTIONS.ROUTE_ACTIVE_USER, null);
}

function frozen(state, action, modelCalls) {
  return Object.freeze({
    state,
    action,
    modelCalls,
    message: MESSAGES[action] || null,
  });
}

module.exports = { ACTIONS, COMMANDS, MESSAGES, STATES, reduceOnboarding };
