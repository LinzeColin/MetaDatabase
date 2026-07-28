"use strict";

// Everything a first-time install needs, created for the user instead of asked
// of them. Before this module, starting CyberBoss meant hand-generating two
// 32-byte key files with the right permissions and hand-writing a workspace
// registry whose schema rejects almost every hand-written document. Neither is
// a decision the person running the software should have to make.
//
// Every step is idempotent and never overwrites: a key that already exists is
// left alone, because regenerating it would orphan every user id derived from
// it and make the existing database unreadable.

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const KEY_BYTES = 32;
const KEY_MODE = 0o600;
const DIR_MODE = 0o700;
// The registry schema is frozen at CB-600 and validated exactly; these are the
// only values that satisfy it, so they are written rather than asked for.
const WORKSPACE_ALIAS = "cyberboss";
const WORKSPACE_DOCUMENT = Object.freeze({
  repo: "LinzeColin/MetaDatabase",
  project_subpath: "CyberBoss",
  max_bytes: 4_294_967_296,
  sparse_paths: ["CyberBoss", ".github"],
  root_integration_paths: [".github"],
  root_integration_write: false,
  write_globs: ["CyberBoss/**"],
});

function defaultStateDir() {
  return process.env.CYBERBOSS_STATE_DIR || path.join(os.homedir(), ".cyberboss");
}

// The workspace base defaults to /srv on a server, which a desktop user cannot
// write to. Under the home directory it always works and needs no root.
function defaultWorkspaceBase(stateDir) {
  return process.env.CYBERBOSS_WORKSPACE_BASE || path.join(stateDir, "workspaces");
}

function ensureDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true, mode: DIR_MODE });
  try {
    fs.chmodSync(directory, DIR_MODE);
  } catch {
    // A directory the installer does not own is left as it is; the key write
    // below is what actually has to be private, and it enforces its own mode.
  }
}

// A key file is created once and then treated as immutable. The Owner user id,
// every user id and the invite secret are all derived from the identity key, so
// replacing it would silently orphan the existing database.
function ensureKeyFile(filePath) {
  ensureDirectory(path.dirname(filePath));
  if (fs.existsSync(filePath)) {
    const stat = fs.lstatSync(filePath);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new BootstrapError("KEY_FILE_INVALID", filePath);
    }
    if (stat.size !== KEY_BYTES) {
      throw new BootstrapError("KEY_FILE_LENGTH_INVALID", filePath);
    }
    if ((stat.mode & 0o077) !== 0) {
      // Repairable rather than fatal: the app refuses a group- or
      // world-readable key, and tightening it is always the right answer.
      fs.chmodSync(filePath, KEY_MODE);
      return { path: filePath, created: false, repaired: true };
    }
    return { path: filePath, created: false, repaired: false };
  }
  const handle = fs.openSync(filePath, "wx", KEY_MODE);
  try {
    fs.writeSync(handle, crypto.randomBytes(KEY_BYTES));
  } finally {
    fs.closeSync(handle);
  }
  fs.chmodSync(filePath, KEY_MODE);
  return { path: filePath, created: true, repaired: false };
}

function ensureWorkspaceRegistry({ configPath, workspaceBase }) {
  const root = path.join(workspaceBase, WORKSPACE_ALIAS);
  ensureDirectory(workspaceBase);
  ensureDirectory(root);
  if (fs.existsSync(configPath)) {
    return { path: configPath, root, created: false };
  }
  ensureDirectory(path.dirname(configPath));
  const document = {
    schema_version: 1,
    default_alias: WORKSPACE_ALIAS,
    workspace_base: workspaceBase,
    workspaces: {
      [WORKSPACE_ALIAS]: { root, ...WORKSPACE_DOCUMENT },
    },
  };
  fs.writeFileSync(configPath, `${JSON.stringify(document, null, 2)}\n`, {
    mode: 0o600,
  });
  return { path: configPath, root, created: true };
}

// Settings are written to the state directory's .env so nothing has to be
// exported by hand and the next run picks them up on its own.
function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return new Map();
  }
  const entries = new Map();
  for (const line of fs.readFileSync(filePath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const index = trimmed.indexOf("=");
    if (index < 1) continue;
    entries.set(trimmed.slice(0, index).trim(), trimmed.slice(index + 1).trim());
  }
  return entries;
}

function writeEnvFile(filePath, entries) {
  ensureDirectory(path.dirname(filePath));
  const body = [...entries]
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  fs.writeFileSync(
    filePath,
    `# CyberBoss 设置。这个文件由 cyberboss setup 维护，可以直接编辑。\n${body}\n`,
    { mode: 0o600 },
  );
}

function updateEnvFile(filePath, updates) {
  const entries = readEnvFile(filePath);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) {
      entries.delete(key);
    } else {
      entries.set(key, String(value));
    }
  }
  writeEnvFile(filePath, entries);
  return entries;
}

class BootstrapError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "BootstrapError";
    this.code = code;
    this.detail = detail;
  }
}

// The single call a first run makes. It provisions everything and reports what
// it had to create, so the wizard can tell the user what just happened.
function bootstrapInstallation({ stateDir = defaultStateDir() } = {}) {
  const workspaceBase = defaultWorkspaceBase(stateDir);
  ensureDirectory(stateDir);
  const credentials = path.join(stateDir, "credentials");
  const encryptionKey = ensureKeyFile(
    process.env.CB_RUNTIME_ENCRYPTION_KEY_FILE
      || path.join(credentials, "runtime-encryption.key"),
  );
  const identityKey = ensureKeyFile(
    process.env.CB_RUNTIME_IDENTITY_KEY_FILE
      || path.join(credentials, "runtime-identity.key"),
  );
  const workspace = ensureWorkspaceRegistry({
    configPath: process.env.CYBERBOSS_WORKSPACE_CONFIG
      || path.join(stateDir, "workspaces.json"),
    workspaceBase,
  });
  const envFile = path.join(stateDir, ".env");
  const existing = readEnvFile(envFile);
  // Written once so the workspace base survives a shell that never exported it.
  if (!existing.has("CYBERBOSS_WORKSPACE_BASE")) {
    updateEnvFile(envFile, { CYBERBOSS_WORKSPACE_BASE: workspaceBase });
  }
  // 后台页面的管理员令牌。生成一次就固定下来——每次重启都换一个的话，
  // 用户存的那个后台书签第二天就打不开了。
  if (!existing.has("CB_ADMIN_TOKEN")) {
    updateEnvFile(envFile, { CB_ADMIN_TOKEN: crypto.randomBytes(24).toString("base64url") });
  }
  // Applied to this process too, so the very first run works without a restart.
  process.env.CYBERBOSS_WORKSPACE_BASE ||= workspaceBase;
  process.env.CYBERBOSS_STATE_DIR ||= stateDir;

  return Object.freeze({
    stateDir,
    workspaceBase,
    envFile,
    encryptionKey,
    identityKey,
    workspace,
    createdAnything:
      encryptionKey.created || identityKey.created || workspace.created,
  });
}

module.exports = {
  BootstrapError,
  KEY_BYTES,
  WORKSPACE_ALIAS,
  bootstrapInstallation,
  defaultStateDir,
  defaultWorkspaceBase,
  ensureKeyFile,
  ensureWorkspaceRegistry,
  readEnvFile,
  updateEnvFile,
};
