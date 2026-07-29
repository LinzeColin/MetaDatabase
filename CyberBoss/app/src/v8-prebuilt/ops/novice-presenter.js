'use strict';

const OPERATOR_COMMANDS = Object.freeze(['install','doctor','start','stop','restart','status','backup','restore','rollback']);

function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function presentUsage({ percent = 0, circuitState = 'closed', connectionState = 'active' } = {}) {
  const used = clampPercent(percent);
  if (connectionState !== 'active') {
    return Object.freeze({ level: 'blocked', title: 'AI 还没有连接好', body: '重新打开连接页面，按提示检查后再试。', action: '重新连接', usedPercent: used });
  }
  if (circuitState === 'open') {
    return Object.freeze({ level: 'degraded', title: 'AI 暂时不可用', body: '系统已经自动暂停请求，避免继续失败或产生额外消耗。', action: '检查连接', usedPercent: used });
  }
  if (used >= 100) {
    return Object.freeze({ level: 'blocked', title: '本次使用额度已到上限', body: '系统已停止新的 AI 请求，不会在后台继续消耗。', action: '查看额度', usedPercent: used });
  }
  if (used >= 80) {
    return Object.freeze({ level: 'warning', title: 'AI 使用额度快到上限', body: `本期已使用约 ${used}%，达到上限后会自动停止。`, action: '查看额度', usedPercent: used });
  }
  return Object.freeze({ level: 'healthy', title: 'AI 使用正常', body: `本期已使用约 ${used}%，达到上限后会自动停止。`, action: '查看详情', usedPercent: used });
}

function validateOperatorSurface(commands) {
  const actual = new Set(commands || []);
  const missing = OPERATOR_COMMANDS.filter((command) => !actual.has(command));
  return Object.freeze({ ok: missing.length === 0, missing, required: [...OPERATOR_COMMANDS] });
}

function operatorResult({ command, ok, reasonCode = null } = {}) {
  if (!OPERATOR_COMMANDS.includes(command)) throw new TypeError('unsupported operator command');
  if (ok) return Object.freeze({ ok: true, title: `${command} 已完成`, next: command === 'install' ? '下一步：运行 status 查看系统状态。' : '无需保持终端或开发 Agent 在线。' });
  const next = reasonCode === 'MISSING_CREDENTIAL' ? '按屏幕上的一次性说明补充凭据，然后重新执行同一命令。' : '运行 doctor 查看唯一修复建议；不要反复重试。';
  return Object.freeze({ ok: false, title: `${command} 未完成`, reasonCode: reasonCode || 'UNKNOWN', next });
}

module.exports = { OPERATOR_COMMANDS, presentUsage, validateOperatorSurface, operatorResult };
