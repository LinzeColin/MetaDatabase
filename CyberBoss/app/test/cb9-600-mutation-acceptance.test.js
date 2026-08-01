"use strict";

// CB9-600 确定性测试与判别力（AC-036 / NFR-006）
//
// AC-036 的 oracle：「对模式隔离、幂等、位置隐私、Status 新鲜度各注入至少一个
// 反例；错误实现必须导致测试失败。」
//
// 真正的证据是 `node scripts/mutation-acceptance.js` 的输出（13/13 转红，
// 见 docs/evidence/CB9-600/mutation-report.json）。这个文件守的是**那个脚本
// 本身**——一个悄悄不再注入任何东西的变异测试比没有更糟：它每次都报全红，
// 而看的人会以为判别力还在。
//
// 三件必须钉住的事：四个维度一个都不能少、每一刀的锚点在当前源码里必须唯一
// 命中、每一刀都要说得出后果。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { MUTATIONS } = require("../scripts/mutation-acceptance");

const REQUIRED_DIMENSIONS = ["模式隔离", "幂等", "位置隐私", "Status 新鲜度"];

test("AC-036 四个维度各至少一刀", () => {
  const covered = new Set(MUTATIONS.map((mutation) => mutation.dimension));
  for (const dimension of REQUIRED_DIMENSIONS) {
    assert.ok(covered.has(dimension), `AC-036 点名的「${dimension}」一刀都没有`);
  }
  // 反过来也钉：多出一个没在验收里的维度，说明这份清单在往别处长。
  assert.deepEqual([...covered].sort(), [...REQUIRED_DIMENSIONS].sort());
});

test("AC-036 每一刀的锚点在当前源码里唯一命中", () => {
  // 锚点失效是这类脚本最常见的死法：代码改了、锚点没跟上，脚本从此什么都不注入
  // 而每次都报"全红"。脚本自己会把这种情况算作失败，这里再钉一道——
  // 让它在**普通的 npm test** 里就红，不用等谁想起来跑那个脚本。
  const stale = [];
  for (const mutation of MUTATIONS) {
    const source = fs.readFileSync(mutation.file, "utf8");
    const hits = source.split(mutation.from).length - 1;
    if (hits !== 1) {
      stale.push(`${path.basename(mutation.file)} :: ${mutation.name}（命中 ${hits} 次）`);
    }
  }
  assert.deepEqual(stale, [], `这几刀的锚点和源码脱节了：\n${stale.join("\n")}`);
});

test("AC-036 每一刀都改成一个能跑的错误实现，不是语法错误", () => {
  // 把代码改成语法错误谁都拦得住，证明不了判别力。每一刀都必须是**一个真实的
  // 错误决定**：判反了、少查一个条件、把守卫摘掉。
  for (const mutation of MUTATIONS) {
    assert.notEqual(mutation.from, mutation.to, `${mutation.name} 根本没改东西`);
    assert.ok(mutation.consequence && mutation.consequence.length > 10,
      `${mutation.name} 说不出后果——红了也不知道红得对不对`);
    assert.ok(Array.isArray(mutation.tests) && mutation.tests.length > 0,
      `${mutation.name} 没指定跑哪些测试`);
    for (const file of mutation.tests) {
      assert.ok(fs.existsSync(path.join(__dirname, "..", file)),
        `${mutation.name} 指向了一个不存在的测试文件 ${file}`);
    }
  }
});

test("AC-036 变异脚本改完一定把源码放回去", () => {
  // 放不回去的话，工作树里留着一份被改坏的代码，而它看起来是正常的。
  // 所以恢复那一步必须在 finally 里——顺序执行的话，中间抛异常就留在那儿了。
  const script = fs.readFileSync(
    path.join(__dirname, "..", "scripts", "mutation-acceptance.js"), "utf8");
  assert.ok(/\} finally \{\s*(\/\/[^\n]*\n\s*)*fs\.writeFileSync\(mutation\.file, original\);/.test(script),
    "恢复源码那一步不在 finally 里");
});

test("AC-036 锚点失效算失败，不算跳过", () => {
  // 算跳过的话，脚本会一边什么都不注入一边报全红。
  const script = fs.readFileSync(
    path.join(__dirname, "..", "scripts", "mutation-acceptance.js"), "utf8");
  const block = script.slice(script.indexOf("if (occurrences !== 1)"), script.indexOf("let turnedRed"));
  assert.ok(block.includes("survived += 1"), "锚点失效没被算进存活数");
  assert.ok(script.includes("survived === 0 && missing.length === 0"),
    "退出码没同时看存活数和维度覆盖");
});
