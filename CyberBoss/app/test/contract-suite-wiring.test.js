"use strict";

// CyberBoss/tests/ 那套契约证据测试烂过一次，而且没人发现。
//
// 根因不是那两条断言写错了，是**没有任何命令会跑它**：app/package.json 的 test
// 是 `node --test`，从 app/ 跑，只覆盖 app/test/。tests/ 要从 CyberBoss 根目录
// 跑才带得上，而那样又会把 vendor/timeline-for-agent/test/ 一起拖进来（那是
// vendored 的第三方项目，本来就不该由我们的套件负责）。
//
// 于是它红了不知道多久，直到 2026-07-29 有人从根目录跑了一次才发现。
//
// 光把那两条断言修好，下次还会一样地烂。所以这里钉的是**接线本身**：
// test:contract 必须存在、必须指向 tests/、必须不碰 vendor/。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const PACKAGE_JSON = path.resolve(__dirname, "..", "package.json");
const CONTRACT_DIR = path.resolve(__dirname, "..", "..", "tests");

function scripts() {
  return JSON.parse(fs.readFileSync(PACKAGE_JSON, "utf8")).scripts || {};
}

test("契约证据套件有一条真的会跑它的命令", () => {
  const command = scripts()["test:contract"];
  assert.ok(command, "test:contract 不见了——tests/ 又会变成没人跑的那套");
  assert.match(command, /tests\//, "test:contract 必须指向 tests/");
  assert.match(command, /node --test/);
});

test("跑契约套件不会把 vendor 拖进来", () => {
  const all = Object.values(scripts()).join(" ");
  assert.doesNotMatch(
    all,
    /vendor\//,
    "vendor/ 是 vendored 的第三方项目，它的红不该由我们的套件承担",
  );
});

test("test:all 同时覆盖两套，缺一不可", () => {
  const command = scripts()["test:all"];
  assert.ok(command, "test:all 不见了");
  assert.match(command, /\btest\b/);
  assert.match(command, /test:contract/);
});

test("tests/ 目录还在，而且不是空的", () => {
  // 有人可能会选择删掉这套。那是个合理的决定，但不能悄悄发生：
  // software-correctness-suite.js 的 FROZEN_CORE_SLICES 按名字引用它们，
  // docs/evidence 和 docs/governance/RUN_CONTRACT_* 也引用了，删了会破坏密封契约。
  const files = fs.readdirSync(CONTRACT_DIR).filter((name) => name.endsWith(".test.js"));
  assert.ok(files.length > 0, "tests/ 空了——先确认 FROZEN_CORE_SLICES 也一起改了");
});

test("FROZEN_CORE_SLICES 点名的每个文件都真的存在", () => {
  // 这套东西的价值全在「它点名的文件真的能跑」。少一个文件，那一片证据就是假的。
  const { FROZEN_CORE_SLICES } = require("../scripts/software-correctness-suite");
  const root = path.resolve(__dirname, "..", "..");
  const missing = [];
  for (const slice of FROZEN_CORE_SLICES) {
    for (const file of slice.test_files) {
      if (!fs.existsSync(path.join(root, file))) {
        missing.push(`${slice.id} → ${file}`);
      }
    }
  }
  assert.deepEqual(missing, [], `冻结切片点名了不存在的文件：\n  ${missing.join("\n  ")}`);
});
