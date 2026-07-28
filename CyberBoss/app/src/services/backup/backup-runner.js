"use strict";

// 把 CB-800 的双副本备份真的跑起来。
//
// 协调器本身要求六件事：快照、加密、解密、校验、隔离恢复、关系验证。之前这六个
// 位置都是测试里的假函数，所以"备份"从来没有把一个真的数据库写到任何地方过。
// 这里是真的那六个。
//
// 一条规则贯穿全文：**两份副本都落地才发收据**。任何一边失败都不给收据——一张
// 声称有两份副本、实际只有一份的收据，会在你真正需要它的那天才暴露。

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const {
  DualCopyBackupCoordinator,
} = require("./dual-copy-receipt");
const { createObjectClients } = require("./object-clients");

const RECEIPTS_DIRNAME = "backups";

class BackupRunnerError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "BackupRunnerError";
    this.code = code;
    this.detail = detail;
  }
}

// SQLite 的 VACUUM INTO 产出的是一个一致的、可直接打开的副本，而不是"复制一个
// 正在被写的文件"。后者在有并发写的时候会拿到一个撕裂的快照。
function snapshotSqlite(databasePath) {
  const target = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), "cb-snap-")),
    "snapshot.db",
  );
  const database = new DatabaseSync(databasePath, { readOnly: true });
  try {
    database.exec(`VACUUM INTO '${target.replaceAll("'", "''")}'`);
  } finally {
    database.close();
  }
  try {
    return fs.readFileSync(target);
  } finally {
    fs.rmSync(path.dirname(target), { recursive: true, force: true });
  }
}

// AES-256-GCM。密钥由本机的 runtime 加密密钥派生，所以云上那份密文离开这台
// 机器就没有意义——即使桶被读走也一样。
function encryptWithKey(key, plain) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const body = Buffer.concat([cipher.update(plain), cipher.final()]);
  return Buffer.concat([Buffer.from("CBBK1"), iv, cipher.getAuthTag(), body]);
}

function decryptWithKey(key, envelope) {
  const buffer = Buffer.from(envelope);
  if (buffer.length < 5 + 12 + 16 || buffer.subarray(0, 5).toString() !== "CBBK1") {
    throw new BackupRunnerError("BACKUP_ENVELOPE_INVALID");
  }
  const iv = buffer.subarray(5, 17);
  const tag = buffer.subarray(17, 33);
  const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(buffer.subarray(33)), decipher.final()]);
}

// 一份"看起来像数据库"的字节流不算有效快照。这里真的把它打开、跑完整性检查、
// 并确认关键表都在——一个坏掉的备份必须在生成的那一刻就被发现，而不是在你
// 需要恢复的那天。
function validateSnapshotBytes(bytes) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-valid-"));
  const file = path.join(directory, "candidate.db");
  try {
    fs.writeFileSync(file, bytes);
    const database = new DatabaseSync(file, { readOnly: true });
    try {
      const integrity = database.prepare("PRAGMA integrity_check").get();
      if (String(integrity.integrity_check).toLowerCase() !== "ok") {
        throw new BackupRunnerError("BACKUP_SNAPSHOT_CORRUPT", integrity.integrity_check);
      }
      for (const table of ["users", "user_channels", "schema_migrations"]) {
        const row = database
          .prepare("SELECT 1 AS present FROM sqlite_master WHERE type='table' AND name=?")
          .get(table);
        if (!row) {
          throw new BackupRunnerError("BACKUP_SNAPSHOT_TABLE_MISSING", table);
        }
      }
    } finally {
      database.close();
    }
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
  return true;
}

// 恢复演练在一个临时目录里进行，绝不碰正在运行的那个数据库。
function restoreIsolated(bytes) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-restore-"));
  const file = path.join(directory, "restored.db");
  fs.writeFileSync(file, bytes);
  return { directory, file };
}

// 恢复出来的库里，用户与渠道绑定的关系必须还成立。字节对得上但外键断了的
// "恢复成功"，是最容易骗过自己的那一种。
function verifyRestoredRelations(handle) {
  const database = new DatabaseSync(handle.file, { readOnly: true });
  try {
    const orphans = database
      .prepare(
        `SELECT COUNT(*) AS count FROM user_channels c
         WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = c.user_id)`,
      )
      .get();
    if (Number(orphans.count) !== 0) {
      throw new BackupRunnerError("RESTORE_ORPHAN_CHANNELS", String(orphans.count));
    }
    const users = database.prepare("SELECT COUNT(*) AS count FROM users").get();
    return Object.freeze({ users: Number(users.count), orphanChannels: 0 });
  } finally {
    database.close();
    fs.rmSync(handle.directory, { recursive: true, force: true });
  }
}

class BackupRunner {
  constructor({ databasePath, encryptionKey, stateDir, config = {}, fetchImpl = globalThis.fetch }) {
    if (typeof databasePath !== "string" || !path.isAbsolute(databasePath)) {
      throw new BackupRunnerError("DATABASE_PATH_MUST_BE_ABSOLUTE");
    }
    if (!Buffer.isBuffer(encryptionKey) || encryptionKey.length < 32) {
      throw new BackupRunnerError("ENCRYPTION_KEY_REQUIRED");
    }
    this.databasePath = databasePath;
    // 备份用的密钥与运行时加密密钥分开派生：一处泄露不会顺带打开另一处。
    this.key = crypto.createHmac("sha256", encryptionKey).update("cyberboss-backup-key").digest();
    this.stateDir = stateDir;
    const clients = createObjectClients(config, { fetchImpl });
    this.missing = clients.missing;
    this.ready = clients.ready;
    this.coordinator = this.ready
      ? new DualCopyBackupCoordinator({
          snapshotRuntimeDb: () => snapshotSqlite(this.databasePath),
          encryptSnapshot: (plain) => encryptWithKey(this.key, plain),
          decryptSnapshot: (envelope) => decryptWithKey(this.key, envelope),
          validateSnapshot: (bytes) => validateSnapshotBytes(bytes),
          restoreRuntimeDbIsolated: (bytes) => restoreIsolated(bytes),
          verifyRelations: (handle) => verifyRestoredRelations(handle),
          r2: clients.r2,
          oci: clients.oci,
        })
      : null;
  }

  // 没配齐就如实说缺什么，而不是跑一个只写了一份副本的"备份"。
  status() {
    return Object.freeze({
      ready: this.ready,
      missing: this.missing,
      reason: this.ready ? "ok" : `BACKUP_TARGET_ABSENT:${this.missing.join(",")}`,
    });
  }

  // releaseId 会进收据并被 CB-800 的格式校验（至少 8 位）挡住。这里给的默认值
  // 本身就合法；调用方传了一个太短的，如实报错而不是替他改掉——收据上的
  // release 编号必须是他真正部署的那一个。
  async run({ releaseId = "local-snapshot", now = () => new Date() } = {}) {
    if (!this.coordinator) {
      throw new BackupRunnerError("BACKUP_TARGET_ABSENT", this.missing.join(","));
    }
    const createdAt = now();
    const backupId = `bk_${createdAt.toISOString().replace(/[^0-9]/g, "").slice(0, 14)}_${crypto.randomBytes(4).toString("hex")}`;
    const receipt = await this.coordinator.create({
      backupId,
      releaseId,
      createdAt: createdAt.toISOString(),
    });
    this.#writeReceipt(receipt);
    return receipt;
  }

  #writeReceipt(receipt) {
    if (!this.stateDir) {
      return null;
    }
    const directory = path.join(this.stateDir, RECEIPTS_DIRNAME);
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    const file = path.join(directory, `${receipt.backupId}.json`);
    fs.writeFileSync(file, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 });
    return file;
  }

  listReceipts() {
    if (!this.stateDir) {
      return [];
    }
    const directory = path.join(this.stateDir, RECEIPTS_DIRNAME);
    if (!fs.existsSync(directory)) {
      return [];
    }
    return fs
      .readdirSync(directory)
      .filter((name) => name.endsWith(".json"))
      .sort()
      .reverse()
      .map((name) => {
        try {
          return JSON.parse(fs.readFileSync(path.join(directory, name), "utf8"));
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }
}

module.exports = {
  BackupRunner,
  BackupRunnerError,
  decryptWithKey,
  encryptWithKey,
  restoreIsolated,
  snapshotSqlite,
  validateSnapshotBytes,
  verifyRestoredRelations,
};
