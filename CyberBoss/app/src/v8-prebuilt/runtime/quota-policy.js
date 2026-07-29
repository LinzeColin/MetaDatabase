'use strict';
const DEFAULTS = Object.freeze({ perUserActive:1, perUserQueued:3, globalProviderActive:2, globalImportActive:1, maxTextBytes:32768 });
function evaluateQuota({ kind, text = '', userActive = 0, userQueued = 0, globalProviderActive = 0, globalImportActive = 0, limits = DEFAULTS }) {
  if (Buffer.byteLength(String(text), 'utf8') > limits.maxTextBytes) return { allowed:false, reason:'消息太长，请分成几条发送。', code:'TEXT_TOO_LARGE', modelCalls:0 };
  if (kind === 'ai') {
    if (userActive >= limits.perUserActive || userQueued >= limits.perUserQueued) return { allowed:false, reason:'你已有任务正在处理，请稍后再发。', code:'USER_QUEUE_FULL', modelCalls:0 };
    if (globalProviderActive >= limits.globalProviderActive) return { allowed:false, reason:'当前使用人数较多，任务已安全排队。', code:'GLOBAL_PROVIDER_BUSY', modelCalls:0 };
  }
  if (kind === 'import' && globalImportActive >= limits.globalImportActive) return { allowed:false, reason:'已有导入任务正在运行，你的文件会按顺序处理。', code:'IMPORT_BUSY', modelCalls:0 };
  return { allowed:true, code:'OK', modelCalls:0 };
}
module.exports = { DEFAULTS, evaluateQuota };
