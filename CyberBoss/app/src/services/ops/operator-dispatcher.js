"use strict";

// CB-830 / AC-050: the Owner's single-command lifecycle surface.
//
// The operator types `cyberbossctl backup`. What runs is not that string: it is
// a fixed command looked up in a root-owned configuration file, executed with
// shell:false, an absolute executable, a sanitised environment and a bounded
// timeout. There is no path from what the operator typed to what the shell
// sees, so there is nothing to inject into.
//
// Every guard here fails closed. A configuration file that is a symlink, that
// is not owned by the expected uid, or that any other user can write, is
// refused before it is parsed — not repaired, not warned about.

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

// Frozen. The documented surface and the implemented surface are the same
// list, so a documented action that was never wired up is a failure rather
// than a surprise at 3am.
const ALLOWED_ACTIONS = Object.freeze([
  "install",
  "doctor",
  "start",
  "stop",
  "restart",
  "status",
  "backup",
  "restore",
  "rollback",
]);

// Bounded per action. A lifecycle command that hangs is killed and reported,
// because an operator staring at a frozen terminal learns nothing.
const ACTION_TIMEOUT_MS = Object.freeze({
  install: 900_000,
  doctor: 120_000,
  start: 120_000,
  stop: 120_000,
  restart: 180_000,
  status: 60_000,
  backup: 900_000,
  restore: 900_000,
  rollback: 300_000,
});

// Nothing inherited. A hostile PATH or LD_PRELOAD in the operator's shell must
// not reach a privileged lifecycle command.
const SAFE_ENV = Object.freeze({
  PATH: "/usr/sbin:/usr/bin:/sbin:/bin",
  LANG: "C.UTF-8",
  LC_ALL: "C.UTF-8",
});

// The only variables allowed through, and only as bounded, clean strings.
const PASSTHROUGH_ENV = Object.freeze([
  "CYBERBOSS_RELEASE_ID",
  "CYBERBOSS_DATA_ROOT",
  "CYBERBOSS_BACKUP_ROOT",
]);

const MAX_COMMAND_PARTS = 12;
const MAX_PART_LENGTH = 500;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;

class OperatorDispatchError extends Error {
  constructor(code, target = null) {
    super(code);
    this.name = "OperatorDispatchError";
    this.code = code;
    this.target = target;
  }
}

// A root-controlled file: not a symlink, owned by the expected uid, and not
// writable by group or other.
function validateRootControlledFile(filePath, { expectedUid = 0, allowSymlink = false } = {}) {
  if (typeof filePath !== "string" || !path.isAbsolute(filePath)) {
    throw new OperatorDispatchError("OPERATOR_ABSOLUTE_PATH_REQUIRED", filePath);
  }
  const linkStat = fs.lstatSync(filePath);
  if (!allowSymlink && linkStat.isSymbolicLink()) {
    // A symlinked config is a config someone else can repoint.
    throw new OperatorDispatchError("OPERATOR_SYMLINK_NOT_ALLOWED", filePath);
  }
  const resolved = fs.realpathSync(filePath);
  const stat = fs.statSync(resolved);
  if (!stat.isFile()) {
    throw new OperatorDispatchError("OPERATOR_FILE_REQUIRED", filePath);
  }
  if (stat.uid !== expectedUid) {
    throw new OperatorDispatchError("OPERATOR_FILE_OWNER_INVALID", filePath);
  }
  if ((stat.mode & 0o022) !== 0) {
    throw new OperatorDispatchError("OPERATOR_FILE_WRITABLE_BY_NON_OWNER", filePath);
  }
  return Object.freeze({
    requested: filePath,
    resolved,
    uid: stat.uid,
    mode: stat.mode & 0o777,
  });
}

function validateActionConfig(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    throw new OperatorDispatchError("OPERATOR_CONFIG_REQUIRED");
  }
  const unknown = Object.keys(config).filter((key) => !ALLOWED_ACTIONS.includes(key));
  if (unknown.length > 0) {
    throw new OperatorDispatchError("OPERATOR_CONFIG_ACTION_NOT_ALLOWED", unknown.join(","));
  }
  const absent = ALLOWED_ACTIONS.filter((action) => !Object.hasOwn(config, action));
  if (absent.length > 0) {
    // A documented action with no command is the failure this catches.
    throw new OperatorDispatchError("OPERATOR_CONFIG_ACTION_MISSING", absent.join(","));
  }
  for (const action of ALLOWED_ACTIONS) {
    const command = config[action];
    if (!Array.isArray(command) || command.length < 1 || command.length > MAX_COMMAND_PARTS) {
      throw new OperatorDispatchError("OPERATOR_COMMAND_SHAPE_INVALID", action);
    }
    if (!path.isAbsolute(String(command[0]))) {
      throw new OperatorDispatchError("OPERATOR_EXECUTABLE_NOT_ABSOLUTE", action);
    }
    for (const part of command) {
      if (
        typeof part !== "string" ||
        part.length < 1 ||
        part.length > MAX_PART_LENGTH ||
        CONTROL_CHARACTERS.test(part)
      ) {
        throw new OperatorDispatchError("OPERATOR_COMMAND_PART_INVALID", action);
      }
    }
  }
  return Object.freeze(
    Object.fromEntries(
      ALLOWED_ACTIONS.map((action) => [action, Object.freeze([...config[action]])]),
    ),
  );
}

function loadActionConfig(
  configPath = "/etc/cyberboss/operator-actions.json",
  { expectedUid = 0, verifyExecutables = true } = {},
) {
  validateRootControlledFile(configPath, { expectedUid, allowSymlink: false });
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch {
    throw new OperatorDispatchError("OPERATOR_CONFIG_NOT_JSON", configPath);
  }
  const config = validateActionConfig(parsed);
  if (verifyExecutables) {
    // The executable is allowed to be a symlink — /usr/bin/systemctl often is —
    // but its target must still be root-owned and not writable by others.
    for (const action of ALLOWED_ACTIONS) {
      validateRootControlledFile(config[action][0], { expectedUid, allowSymlink: true });
    }
  }
  return config;
}

function buildSafeEnvironment(extra = {}) {
  const permitted = {};
  for (const key of PASSTHROUGH_ENV) {
    const value = extra[key];
    if (
      typeof value === "string" &&
      value.length > 0 &&
      value.length <= MAX_PART_LENGTH &&
      !CONTROL_CHARACTERS.test(value)
    ) {
      permitted[key] = value;
    }
  }
  return Object.freeze({ ...SAFE_ENV, ...permitted });
}

function runOperatorAction({ action, config, runner = spawnSync, environment = {} }) {
  if (!ALLOWED_ACTIONS.includes(action)) {
    throw new OperatorDispatchError("OPERATOR_ACTION_NOT_ALLOWED", String(action));
  }
  const commands = validateActionConfig(config);
  const [executable, ...args] = commands[action];
  const result = runner(executable, args, {
    shell: false,
    stdio: "inherit",
    env: buildSafeEnvironment(environment),
    timeout: ACTION_TIMEOUT_MS[action],
    killSignal: "SIGTERM",
  });
  const timedOut = Boolean(result && result.error && result.error.code === "ETIMEDOUT");
  const code = timedOut ? 124 : Number.isInteger(result && result.status) ? result.status : 1;
  if (code !== 0) {
    return Object.freeze({
      ok: false,
      action,
      code,
      timedOut,
      // One repair action, in plain Chinese, with no jargon and no retry loop.
      title: timedOut ? `${action} 已安全停止` : `${action} 未完成`,
      next: "运行 cyberbossctl doctor 获取唯一修复建议；不要反复重试。",
      modelCalls: 0,
    });
  }
  return Object.freeze({
    ok: true,
    action,
    code: 0,
    timedOut: false,
    title: `${action} 已完成`,
    next: "无需保持终端或开发 Agent 在线。",
    modelCalls: 0,
  });
}

module.exports = {
  ACTION_TIMEOUT_MS,
  ALLOWED_ACTIONS,
  MAX_COMMAND_PARTS,
  MAX_PART_LENGTH,
  OperatorDispatchError,
  PASSTHROUGH_ENV,
  SAFE_ENV,
  buildSafeEnvironment,
  loadActionConfig,
  runOperatorAction,
  validateActionConfig,
  validateRootControlledFile,
};
