"use strict";

// 启动时不许抹掉已有的组穿越位（F18）
//
// /var/lib/cyberboss 底下有几个目录是**按组共享**给别的服务的：canonical-sync
// 以 cyberboss-data:cyberboss 的身份跑，它要穿过 /var/lib/cyberboss 才够得着
// 自己那个 0770 的子目录。
//
// ensureDirectory 原来无条件 chmod 0700，把组的 x 位抹掉——子目录权限设得再对
// 也没用，**穿不过去**。而 EACCES 只报最里面那一跳，不说是哪一级挡的。
//
// 最要命的是它会复发：手工 chmod 0710 修好，下一次部署这个函数原样改回 0700，
// 服务第二天又红。2026-08-02 那天我修了两次才想到来看这个函数。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const bootstrapSource = fs.readFileSync(
  path.join(__dirname, "..", "src", "core", "bootstrap.js"), "utf8");

test("F18 已经放开的组穿越位，启动时要保住", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb-dirmode-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const shared = path.join(root, "state");
  fs.mkdirSync(shared, { mode: 0o700 });
  fs.chmodSync(shared, 0o710);

  // 借 ensureKeyFile 走到 ensureDirectory——那是它真实的调用路径之一。
  const { __ensureDirectoryForTest } = require("../src/core/bootstrap");
  const ensure = __ensureDirectoryForTest;
  assert.equal(typeof ensure, "function", "bootstrap 没有把 ensureDirectory 暴露出来");
  ensure(shared);

  const mode = fs.statSync(shared).mode & 0o777;
  assert.equal(mode, 0o710,
    `启动后变成了 ${mode.toString(8)}——组穿越位被抹掉，按组共享的服务会 EACCES`);
});

test("F18 该关的还是关着：组不许读、不许写，other 一位都没有", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb-dirmode2-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const loose = path.join(root, "loose");
  fs.mkdirSync(loose, { mode: 0o777 });
  fs.chmodSync(loose, 0o777);

  const { __ensureDirectoryForTest: ensure } = require("../src/core/bootstrap");
  ensure(loose);

  const mode = fs.statSync(loose).mode & 0o777;
  assert.equal(mode & 0o007, 0, "other 还有权限");
  assert.equal(mode & 0o040, 0, "组还能读——那就能列出目录内容");
  assert.equal(mode & 0o020, 0, "组还能写这一级");
  assert.equal(mode & 0o010, 0o010, "组的穿越位被抹掉了（这一个目录本来就有）");
});

test("F18 保住的只有穿越位这一位，不是「原样不动」", () => {
  // 「已有权限一律保留」会把一个 0777 的目录原样留着。
  // 结构性地盯住那个掩码：只允许 0o010 这一位被保留。
  const start = bootstrapSource.indexOf("const DIR_GROUP_TRAVERSE");
  assert.ok(start > 0, "找不到那个掩码常量");
  assert.match(bootstrapSource.slice(start, start + 60), /DIR_GROUP_TRAVERSE = 0o010/,
    "保留的掩码不是「只有组穿越位」");
  const fn = bootstrapSource.slice(bootstrapSource.indexOf("function ensureDirectory"));
  assert.ok(fn.includes("DIR_MODE | keep"), "chmod 的目标不是「基准模式 + 保留位」");
});
