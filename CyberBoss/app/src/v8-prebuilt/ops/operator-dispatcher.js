'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const ALLOWED_ACTIONS = Object.freeze(['install','doctor','start','stop','restart','status','backup','restore','rollback']);
const ACTION_TIMEOUT_MS = Object.freeze({
  install: 900000,
  doctor: 120000,
  start: 120000,
  stop: 120000,
  restart: 180000,
  status: 60000,
  backup: 900000,
  restore: 900000,
  rollback: 300000,
});
const SAFE_ENV = Object.freeze({ PATH: '/usr/sbin:/usr/bin:/sbin:/bin', LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8' });

function ownershipError(code, target) {
  return Object.assign(new Error(code), { code, target });
}

function validateRootControlledFile(filePath, { expectedUid = 0, allowSymlink = false } = {}) {
  if (!path.isAbsolute(filePath)) throw new TypeError('absolute path required');
  const linkStat = fs.lstatSync(filePath);
  if (!allowSymlink && linkStat.isSymbolicLink()) throw ownershipError('OPERATOR_SYMLINK_NOT_ALLOWED', filePath);
  const resolved = fs.realpathSync(filePath);
  const stat = fs.statSync(resolved);
  if (!stat.isFile()) throw ownershipError('OPERATOR_FILE_REQUIRED', filePath);
  if (stat.uid !== expectedUid) throw ownershipError('OPERATOR_FILE_OWNER_INVALID', filePath);
  if ((stat.mode & 0o022) !== 0) throw ownershipError('OPERATOR_FILE_WRITABLE_BY_NON_OWNER', filePath);
  return Object.freeze({ requested: filePath, resolved, uid: stat.uid, mode: stat.mode & 0o777 });
}

function validateActionConfig(config) {
  if (!config || typeof config !== 'object' || Array.isArray(config)) throw new TypeError('operator action config required');
  const unknown = Object.keys(config).filter((key) => !ALLOWED_ACTIONS.includes(key));
  if (unknown.length) throw Object.assign(new Error('OPERATOR_CONFIG_ACTION_NOT_ALLOWED'), { code: 'OPERATOR_CONFIG_ACTION_NOT_ALLOWED', unknown });
  for (const action of ALLOWED_ACTIONS) {
    const command = config[action];
    if (!Array.isArray(command) || command.length < 1 || command.length > 12) throw new TypeError(`command array required for ${action}`);
    if (!path.isAbsolute(command[0])) throw new TypeError(`absolute executable required for ${action}`);
    for (const part of command) {
      if (typeof part !== 'string' || part.length < 1 || part.length > 500 || /[\u0000\r\n]/.test(part)) throw new TypeError(`invalid command part for ${action}`);
    }
  }
  return Object.freeze(Object.fromEntries(ALLOWED_ACTIONS.map((action) => [action, Object.freeze([...config[action]])])));
}

function loadActionConfig(configPath = '/etc/cyberboss/operator-actions.json', { expectedUid = 0, verifyExecutables = true } = {}) {
  validateRootControlledFile(configPath, { expectedUid, allowSymlink: false });
  const config = validateActionConfig(JSON.parse(fs.readFileSync(configPath, 'utf8')));
  if (verifyExecutables) {
    for (const action of ALLOWED_ACTIONS) validateRootControlledFile(config[action][0], { expectedUid, allowSymlink: true });
  }
  return config;
}

function buildSafeEnvironment(extra = {}) {
  const permitted = {};
  for (const key of ['CYBERBOSS_RELEASE_ID', 'CYBERBOSS_DATA_ROOT', 'CYBERBOSS_BACKUP_ROOT']) {
    if (typeof extra[key] === 'string' && extra[key].length <= 500 && !/[\u0000\r\n]/.test(extra[key])) permitted[key] = extra[key];
  }
  return Object.freeze({ ...SAFE_ENV, ...permitted });
}

function runOperatorAction({ action, config, runner = spawnSync, environment = {} }) {
  if (!ALLOWED_ACTIONS.includes(action)) throw Object.assign(new Error('OPERATOR_ACTION_NOT_ALLOWED'), { code: 'OPERATOR_ACTION_NOT_ALLOWED' });
  const commands = validateActionConfig(config);
  const [executable, ...args] = commands[action];
  const result = runner(executable, args, {
    shell: false,
    stdio: 'inherit',
    env: buildSafeEnvironment(environment),
    timeout: ACTION_TIMEOUT_MS[action],
    killSignal: 'SIGTERM',
  });
  const timedOut = Boolean(result && result.error && result.error.code === 'ETIMEDOUT');
  const code = timedOut ? 124 : (Number.isInteger(result && result.status) ? result.status : 1);
  if (code !== 0) return Object.freeze({
    ok: false,
    action,
    code,
    title: timedOut ? `${action} 已安全停止` : `${action} 未完成`,
    next: '运行 cyberbossctl doctor 获取唯一修复建议；不要反复重试。',
  });
  return Object.freeze({ ok: true, action, code: 0, title: `${action} 已完成`, next: '无需保持终端或开发 Agent 在线。' });
}

module.exports = {
  ALLOWED_ACTIONS,
  ACTION_TIMEOUT_MS,
  SAFE_ENV,
  validateRootControlledFile,
  validateActionConfig,
  loadActionConfig,
  buildSafeEnvironment,
  runOperatorAction,
};
