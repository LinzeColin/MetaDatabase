const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { normalizeAccountId } = require("./account-store");

const MAX_CURSOR_BYTES = 4096;
const NUMERIC_CURSOR = /^(?:0|[1-9][0-9]*)$/;

class SyncBufferStoreError extends Error {
  constructor(code) {
    super(code);
    this.name = "SyncBufferStoreError";
    this.code = code;
  }
}

function normalizeCursor(value) {
  if (typeof value !== "string") {
    throw new SyncBufferStoreError("CURSOR_STRING_REQUIRED");
  }
  const normalized = value.trim();
  if (
    normalized.includes("\u0000")
    || Buffer.byteLength(normalized, "utf8") > MAX_CURSOR_BYTES
  ) {
    throw new SyncBufferStoreError("CURSOR_INVALID");
  }
  return normalized;
}

function ensureSyncBufferDir(config) {
  if (
    typeof config?.syncBufferDir !== "string"
    || !path.isAbsolute(config.syncBufferDir)
  ) {
    throw new SyncBufferStoreError("CURSOR_DIRECTORY_ABSOLUTE_REQUIRED");
  }
  if (
    fs.existsSync(config.syncBufferDir)
    && fs.lstatSync(config.syncBufferDir).isSymbolicLink()
  ) {
    throw new SyncBufferStoreError("CURSOR_DIRECTORY_SYMLINK_FORBIDDEN");
  }
  fs.mkdirSync(config.syncBufferDir, { recursive: true, mode: 0o700 });
  fs.chmodSync(config.syncBufferDir, 0o700);
}

function resolveSyncBufferPath(config, accountId) {
  ensureSyncBufferDir(config);
  return path.join(config.syncBufferDir, `${normalizeAccountId(accountId)}.txt`);
}

function loadSyncBuffer(config, accountId) {
  const filePath = resolveSyncBufferPath(config, accountId);
  if (!fs.existsSync(filePath)) {
    return "";
  }
  const stat = fs.lstatSync(filePath);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new SyncBufferStoreError("CURSOR_FILE_INVALID");
  }
  if (stat.size > MAX_CURSOR_BYTES) {
    throw new SyncBufferStoreError("CURSOR_INVALID");
  }
  return normalizeCursor(fs.readFileSync(filePath, "utf8"));
}

function compareNumericCursor(current, candidate) {
  if (!NUMERIC_CURSOR.test(current) || !NUMERIC_CURSOR.test(candidate)) {
    return null;
  }
  const currentValue = BigInt(current);
  const candidateValue = BigInt(candidate);
  return candidateValue === currentValue
    ? 0
    : candidateValue > currentValue
      ? 1
      : -1;
}

function fsyncDirectory(directory) {
  const directoryFd = fs.openSync(directory, fs.constants.O_RDONLY);
  try {
    fs.fsyncSync(directoryFd);
  } finally {
    fs.closeSync(directoryFd);
  }
}

function processIsAlive(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function removeStaleLock(lockPath) {
  const entries = fs.readdirSync(lockPath);
  if (entries.some((entry) => entry !== "owner.json")) {
    throw new SyncBufferStoreError("CURSOR_LOCK_INVALID");
  }
  const ownerPath = path.join(lockPath, "owner.json");
  if (fs.existsSync(ownerPath)) {
    const stat = fs.lstatSync(ownerPath);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new SyncBufferStoreError("CURSOR_LOCK_INVALID");
    }
    fs.unlinkSync(ownerPath);
  }
  fs.rmdirSync(lockPath);
}

function acquireCursorLock(filePath) {
  const lockPath = `${filePath}.lock`;
  const token = crypto.randomBytes(16).toString("hex");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    let created = false;
    try {
      fs.mkdirSync(lockPath, { mode: 0o700 });
      created = true;
      const ownerPath = path.join(lockPath, "owner.json");
      fs.writeFileSync(
        ownerPath,
        JSON.stringify({ pid: process.pid, token }),
        { encoding: "utf8", mode: 0o600, flag: "wx" },
      );
      fsyncDirectory(lockPath);
      fsyncDirectory(path.dirname(lockPath));
      return Object.freeze({ lockPath, ownerPath, token });
    } catch (error) {
      if (created) {
        try {
          removeStaleLock(lockPath);
          fsyncDirectory(path.dirname(lockPath));
        } catch {
          throw new SyncBufferStoreError("CURSOR_LOCK_INITIALIZATION_FAILED");
        }
      }
      if (error?.code !== "EEXIST") {
        throw error;
      }
      let stat;
      try {
        stat = fs.lstatSync(lockPath);
      } catch (statError) {
        if (statError?.code === "ENOENT") {
          continue;
        }
        throw statError;
      }
      if (stat.isSymbolicLink() || !stat.isDirectory()) {
        throw new SyncBufferStoreError("CURSOR_LOCK_INVALID");
      }
      let owner = null;
      try {
        owner = JSON.parse(
          fs.readFileSync(path.join(lockPath, "owner.json"), "utf8"),
        );
      } catch {
        // A creator killed before the owner record is a recoverable stale lock.
      }
      if (processIsAlive(Number(owner?.pid))) {
        throw new SyncBufferStoreError("CURSOR_COMMIT_LOCKED");
      }
      const stalePath = `${lockPath}.stale.${process.pid}.${token}`;
      try {
        fs.renameSync(lockPath, stalePath);
      } catch (renameError) {
        if (renameError?.code === "ENOENT") {
          continue;
        }
        throw renameError;
      }
      removeStaleLock(stalePath);
      fsyncDirectory(path.dirname(lockPath));
    }
  }
  throw new SyncBufferStoreError("CURSOR_COMMIT_LOCKED");
}

function releaseCursorLock(lock) {
  let owner;
  try {
    owner = JSON.parse(fs.readFileSync(lock.ownerPath, "utf8"));
  } catch {
    throw new SyncBufferStoreError("CURSOR_LOCK_OWNERSHIP_LOST");
  }
  if (owner?.pid !== process.pid || owner?.token !== lock.token) {
    throw new SyncBufferStoreError("CURSOR_LOCK_OWNERSHIP_LOST");
  }
  fs.unlinkSync(lock.ownerPath);
  fs.rmdirSync(lock.lockPath);
  fsyncDirectory(path.dirname(lock.lockPath));
}

function commitSyncBuffer(config, accountId, { expected = "", candidate = "" } = {}) {
  const normalizedExpected = normalizeCursor(expected);
  const normalizedCandidate = normalizeCursor(candidate);
  const filePath = resolveSyncBufferPath(config, accountId);
  const lock = acquireCursorLock(filePath);
  try {
    const current = loadSyncBuffer(config, accountId);
    if (current !== normalizedExpected) {
      throw new SyncBufferStoreError("CURSOR_COMPARE_AND_SET_FAILED");
    }
    if (compareNumericCursor(current, normalizedCandidate) === -1) {
      throw new SyncBufferStoreError("CURSOR_REGRESSION");
    }
    if (current === normalizedCandidate) {
      return Object.freeze({
        previous: current,
        committed: current,
        changed: false,
      });
    }

    const temporary = path.join(
      path.dirname(filePath),
      `.${path.basename(filePath)}.${process.pid}.${crypto.randomBytes(8).toString("hex")}.tmp`,
    );
    const noFollow = fs.constants.O_NOFOLLOW || 0;
    let fd = null;
    try {
      fd = fs.openSync(
        temporary,
        fs.constants.O_WRONLY
          | fs.constants.O_CREAT
          | fs.constants.O_EXCL
          | noFollow,
        0o600,
      );
      const encoded = Buffer.from(normalizedCandidate, "utf8");
      fs.writeSync(fd, encoded, 0, encoded.length, 0);
      fs.fsyncSync(fd);
      fs.fchmodSync(fd, 0o600);
      fs.closeSync(fd);
      fd = null;
      if (fs.existsSync(filePath) && fs.lstatSync(filePath).isSymbolicLink()) {
        throw new SyncBufferStoreError("CURSOR_FILE_SYMLINK_FORBIDDEN");
      }
      fs.renameSync(temporary, filePath);
      fsyncDirectory(path.dirname(filePath));
    } finally {
      if (fd !== null) {
        fs.closeSync(fd);
      }
      if (fs.existsSync(temporary)) {
        fs.unlinkSync(temporary);
      }
    }
    return Object.freeze({
      previous: current,
      committed: normalizedCandidate,
      changed: true,
    });
  } finally {
    releaseCursorLock(lock);
  }
}

function saveSyncBuffer(config, accountId, buffer) {
  const current = loadSyncBuffer(config, accountId);
  return commitSyncBuffer(config, accountId, {
    expected: current,
    candidate: normalizeCursor(String(buffer || "")),
  });
}

module.exports = {
  SyncBufferStoreError,
  commitSyncBuffer,
  loadSyncBuffer,
  normalizeCursor,
  resolveSyncBufferPath,
  saveSyncBuffer,
};
