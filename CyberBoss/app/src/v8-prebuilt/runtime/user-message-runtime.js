'use strict';
const crypto = require('node:crypto');
const { bindReplyRoute } = require('../channel/reply-route-binding');
const { resolveNoviceCommand } = require('../commands/novice-command-map');

function messageText(message) {
  return (Array.isArray(message?.item_list) ? message.item_list : [])
    .map((item) => item?.text_item?.text || item?.voice_item?.text || '')
    .join('\n').trim();
}

const PUBLIC_ERRORS = Object.freeze({
  USER_CAPACITY_FULL: 'CyberBoss 当前只开放 5 个名额，名额已满。',
  GLOBAL_DAILY_TOKEN_CAP: '今天的全局 AI 用量已经达到 10 亿 Token，UTC 零点后自动恢复。',
  DEEPSEEK_CIRCUIT_OPEN: 'DeepSeek 暂时不可用，系统已自动停止继续请求。稍后再试即可。',
  DEEPSEEK_CIRCUIT_PROBE_BUSY: 'DeepSeek 正在恢复检查，请稍后再试。',
  OWNER_DEEPSEEK_KEY_MISSING: 'DeepSeek 尚未完成服务端配置，请联系管理员。',
  DEEPSEEK_KEY_INVALID: 'DeepSeek 服务端密钥无效，请联系管理员。',
  DEEPSEEK_BALANCE_EXHAUSTED: 'DeepSeek 账户余额不足，请联系管理员。',
  DEEPSEEK_RATE_LIMITED: 'DeepSeek 当前请求较多，请稍后再试。',
  DEEPSEEK_TIMEOUT: 'DeepSeek 响应超时，请稍后再试。',
});

const FIXED_COMMAND_REPLIES = Object.freeze({
  help: '直接发一句话就可以。例：帮我整理今天的事情；提醒我下午三点交作业；记录我刚完成了什么。发送“AI状态”可查看当前模型。',
  'ai.status': 'CyberBoss 统一使用 DeepSeek V4 Pro（高推理强度），不需要你提供 API Key，也不能自行切换模型。',
});

class UserMessageRuntime {
  constructor({ sharedController, userRepository, replyOutbox, encrypt, routeKey, commandHandler = null }) {
    if (!sharedController || !userRepository || !replyOutbox || typeof encrypt !== 'function' || !routeKey) throw new TypeError('shared runtime dependencies are required');
    if (commandHandler !== null && typeof commandHandler !== 'function') throw new TypeError('commandHandler must be a function');
    Object.assign(this, { sharedController, userRepository, replyOutbox, encrypt, routeKey, commandHandler });
  }

  async handle({ userId, accountId, message }) {
    const text = messageText(message);
    if (!text) return { action: 'ignored_non_text', modelCalls: 0 };
    const user = this.userRepository.getById(userId);
    if (!user || user.status !== 'active') return this.stage({ userId, accountId, message, text: '请先发送“开始”完成开通。', suffix: 'not-active', modelCalls: 0 });

    const command = resolveNoviceCommand(text);
    if (command && command !== 'onboarding.start') {
      if (FIXED_COMMAND_REPLIES[command]) {
        return this.stage({ userId, accountId, message, text: FIXED_COMMAND_REPLIES[command], suffix: `command-${command.replace(/[^a-z0-9]+/g, '-')}`, modelCalls: 0 });
      }
      if (this.commandHandler) {
        const handled = await this.commandHandler({ command, user, userId, accountId, message, text });
        if (handled && typeof handled.text === 'string') {
          return this.stage({ userId, accountId, message, text: handled.text, suffix: `command-${command.replace(/[^a-z0-9]+/g, '-')}`, modelCalls: Number(handled.modelCalls || 0), runtimeResult: handled });
        }
      }
      return this.stage({ userId, accountId, message, text: '这个功能暂时无法打开，请稍后再试；普通聊天仍可继续使用。', suffix: 'command-unavailable', modelCalls: 0 });
    }

    const requestId = `wx:${accountId}:${message.message_id || message.msg_id || crypto.createHash('sha256').update(`${userId}\0${text}`).digest('hex')}`;
    const result = await this.sharedController.execute({
      userId,
      role: user.role,
      requestId,
      messages: [{ role: 'user', content: text }],
    });
    const reply = result.ok ? result.result.outputText : (PUBLIC_ERRORS[result.code] || 'AI 暂时无法回复，请稍后再试。');
    return this.stage({ userId, accountId, message, text: reply, suffix: 'deepseek-reply', modelCalls: result.providerCalls || 0, runtimeResult: result });
  }

  stage({ userId, accountId, message, text, suffix, modelCalls, runtimeResult = null }) {
    const toUserId = String(message.from_user_id || ''); const contextToken = String(message.context_token || '');
    const route = bindReplyRoute({ routeKey: this.routeKey, userId, botAccountId: accountId, senderId: toUserId, contextToken });
    const key = `${suffix}:${accountId}:${message.message_id || message.msg_id || toUserId}`;
    this.replyOutbox.stage({
      userId, accountId, destinationHash: route.destinationHash, idempotencyKey: key,
      bodyCiphertext: this.encrypt({ scope: `outbox:${accountId}:${key}`, value: { toUserId, contextToken, text } }),
    });
    return { action: 'reply_queued', modelCalls, runtimeResult };
  }
}

module.exports = { UserMessageRuntime, messageText, PUBLIC_ERRORS, FIXED_COMMAND_REPLIES };
