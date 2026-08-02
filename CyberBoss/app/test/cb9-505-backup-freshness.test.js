"use strict";

// 冷备这一行必须由真实回执判，不由「配好了没有」判（AC-026 / AC-035 / F13）
//
// 2026-08-01T23:53 起，cyberboss-backup 连续以 CB530_R2_PUT_FAILED 退出，异地
// 副本停在 07-29。而这整整四天里，Status 上的 backup_restore 一直是 healthy。
//
// 两处各错一半，合起来就完全看不见：
//
//   一、readLatestBackupAt 读的是**快照目录**。本地打包成功、上传失败时，
//       backup_* 目录照样在、时间戳照样新——于是它每天都报告「刚备份过」。
//
//   二、backup_restore 判的是 `backupConfigured ? "healthy" : ...`，而
//       backupConfigured 的意思只是「备份器构造出来了」。
//
// 这个文件自己在 LINE_NOTES 里给 backup_restore 写的口径是
// "receipt only when both copies land"——意图早就写下来了，代码没照做。
// 而这正是 AC-026 明令禁止的配置性伪绿。
//
// 冷备的全部意义是**不在同一台机器上**。本地快照和生产库同机，那台机器没了，
// 两份一起没。所以量的必须是异地那一份。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { projectLiveStatus } = require("../src/services/status/live-status-projector");

const lineOf = (facts, id = "backup_restore") => {
  const projected = projectLiveStatus({ facts });
  const status = projected.status || projected;
  const lines = status.business_lines || status.capabilities || [];
  return lines.find((l) => (l.business_line || l.capability_id) === id);
};
const hoursAgo = (h) => new Date(Date.now() - h * 3600e3).toISOString();

test("AC-026 备份器配好了不等于备份成功了", () => {
  // 这一条是 F13 的核心。配置绿是 AC-026 明令禁止的。
  const line = lineOf({ backupConfigured: true, backupLastSuccessAt: null });
  assert.notEqual(line.state, "healthy",
    "只要备份器构造出来了就显示健康——异地冷备停四天也看不出来");
  assert.equal(line.state, "activation_pending");
  assert.equal(line.reason_code, "BACKUP_NEVER_COMPLETED");
});

test("AC-025 四档按异地副本的新鲜度分开，不是二值", () => {
  // 「还没跑起来」「刚成功过」「漏了一两次」「连着三天没有异地副本」
  // 要的处置完全不同。挤成两态，第四种就永远说不出口。
  assert.equal(lineOf({ backupConfigured: false }).state, "not_started");
  assert.equal(lineOf({ backupConfigured: true, backupLastSuccessAt: hoursAgo(2) }).state, "healthy");
  assert.equal(lineOf({ backupConfigured: true, backupLastSuccessAt: hoursAgo(40) }).state, "degraded");
  const dead = lineOf({ backupConfigured: true, backupLastSuccessAt: hoursAgo(96) });
  assert.equal(dead.state, "blocked");
  assert.equal(dead.reason_code, "BACKUP_OFFSITE_MISSING");
});

test("F13 复现：生产当时那个时间差必须判成红的", () => {
  // 最后一次成功异地上传 2026-07-29T03:35Z；发现时是 2026-08-02T03:00Z。
  // 差 95.4 小时。修好之前这一格是 healthy。
  const line = lineOf({
    backupConfigured: true,
    backupLastSuccessAt: new Date(Date.now() - 95.4 * 3600e3).toISOString(),
  });
  assert.equal(line.state, "blocked", "F13 当时的时间差没有被判成红的");
});

test("回执比现在还新时不当成健康", () => {
  // 钟不对，或者文件被人动过。这时候「健康」是没有依据的。
  const line = lineOf({ backupConfigured: true, backupLastSuccessAt: hoursAgo(-5) });
  assert.equal(line.state, "degraded");
  assert.equal(line.reason_code, "BACKUP_RECEIPT_IN_FUTURE");
});

test("F13 另一半：新鲜度量的是回执目录，不是快照目录", (t) => {
  // 快照目录在本地打包成功就有了，上传失败照样在。只读它的话，
  // 异地停摆期间它每天都报告「刚备份过」。
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb-backup-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  // 只有本地快照，没有任何回执 —— 也就是上传一直在失败的样子。
  fs.mkdirSync(path.join(root, "backup_localonly"), { recursive: true });

  const app = Object.create(CyberbossApp.prototype);
  app.config = { backupLocalDir: root, stateDir: root };
  assert.equal(CyberbossApp.prototype.readLatestBackupAt.call(app), "",
    "只有本地快照时报告了一个成功时间——异地停摆会被当成刚备份过");

  // 有回执了才算数。
  fs.mkdirSync(path.join(root, "receipts"), { recursive: true });
  fs.writeFileSync(path.join(root, "receipts", "backup_x.json"), "{}");
  const at = CyberbossApp.prototype.readLatestBackupAt.call(app);
  assert.ok(at, "有回执了却读不出时间");
  assert.ok(Number.isFinite(Date.parse(at)), "读出来的不是一个时间");
});

test("collectStatusFacts 真的把这个 fact 交出去了", () => {
  // 算得对但没人交上去，等于没算——这一程已经栽过两次（会话层、回执层）。
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = source.indexOf("  collectStatusFacts() {");
  const body = source.slice(start, source.indexOf("\n  }\n", start));
  assert.ok(body.includes("backupLastSuccessAt: this.readLatestBackupAt()"),
    "collectStatusFacts 没交出 backupLastSuccessAt——投影那边永远拿 null");
});
