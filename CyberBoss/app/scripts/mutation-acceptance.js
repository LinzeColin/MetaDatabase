#!/usr/bin/env node
"use strict";

// AC-036 测试判别力（CB9-600 / NFR-006）。
//
// oracle：「对**模式隔离、幂等、位置隐私、Status 新鲜度**各注入至少一个反例；
// 错误实现必须导致测试失败。」
//
// 为什么这条验收本身要存在：
//
// 一套全绿的测试可以什么都不证明。测的是模块自己的性质、断言松到任何实现都满足、
// 或者守卫压根没接到真实链路上——三种情况下套件都是绿的，而产品是坏的。这一程里
// 三种全都撞见过。
//
// 唯一能反驳「这套测试其实没在测东西」的证据，是**把实现改坏，看测试红不红**。
//
// 这个脚本和之前逐节点手跑的红绿不同：它是**提交进仓库的**，任何人任何时候
// `node scripts/mutation-acceptance.js` 都能重跑出同一份结论。手跑的那种只存在于
// 某一次会话的记录里，而一份复现不了的证据在几周后等于没有。
//
// 用法：
//   node scripts/mutation-acceptance.js              跑全部四个维度
//   node scripts/mutation-acceptance.js --json out   同时写一份报告

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const APP = path.join(__dirname, "..");
const src = (relative) => path.join(APP, "src", relative);

// 四个维度，每个至少一刀，每刀都是**一个真实的错误实现**——不是把代码改成语法
// 错误，也不是删掉一整个函数。那两种谁都拦得住，证明不了判别力。
//
// 每一刀都要写清「这样改了会怎样」：一个说不出后果的变异，红了也不知道红得对不对。
const MUTATIONS = Object.freeze([
  // ── 一、模式隔离 ────────────────────────────────────────
  {
    dimension: "模式隔离",
    name: "访客那一格报主人的健康度",
    consequence: "主人的 Codex 好好的会盖住访客那条断掉的路，而主人自己永远看不出来",
    file: src("services/status/live-status-projector.js"),
    from: 'const ownerOnly = businessLine === "owner_codex_runtime" && mode === "COMPANION";',
    to: "const ownerOnly = false;",
    tests: ["test/cb9-510-status-vertical-matrix.test.js"],
  },
  {
    dimension: "模式隔离",
    name: "矩阵完整性只按能力查，不按模式",
    consequence: "一整个模式的格子全缺也算完整，那半边的故障在面板上不存在",
    file: src("services/status/business-matrix.js"),
    from: "const seen = built.map((line) => `${line.business_line}:${line.mode}`);",
    to: "const seen = built.map((line) => `${line.business_line}`);",
    tests: ["test/cb9-510-status-vertical-matrix.test.js", "test/cb810-status-resource-selfheal.test.js"],
  },
  {
    dimension: "模式隔离",
    name: "压回一行时取更好的那个",
    consequence: "访客那条坏路被主人那条好路盖住——而访客坏了正是没人会注意到的情况",
    file: src("services/status/business-matrix.js"),
    from: "|| (STATE_SEVERITY[cell.state] ?? 4) > (STATE_SEVERITY[previous.state] ?? 4)",
    to: "|| (STATE_SEVERITY[cell.state] ?? 4) < (STATE_SEVERITY[previous.state] ?? 4)",
    tests: ["test/cb9-510-status-vertical-matrix.test.js"],
  },

  // ── 二、幂等 ────────────────────────────────────────────
  {
    dimension: "幂等",
    name: "幂等键掺进时间",
    consequence: "重启后同一件事算出新键，被当成新任务重做一遍",
    file: src("services/outbox/unknown-result.js"),
    from: '.update(parts.join("\\u0000")).digest("hex").slice(0, 32)}`;',
    to: '.update(`${parts.join("\\u0000")}${Date.now()}`).digest("hex").slice(0, 32)}`;',
    tests: ["test/cb9-450-idempotency-reconcile.test.js"],
  },
  {
    dimension: "幂等",
    name: "不知道成没成时当失败重试",
    consequence: "超时的那条会被重发，用户收到两条一模一样的",
    file: src("services/outbox/unknown-result.js"),
    from: '    return Object.freeze({ result: "unknown", reason: "transport_interrupted" });',
    to: '    return Object.freeze({ result: "failed", reason: "transport_interrupted" });',
    tests: ["test/cb9-450-idempotency-reconcile.test.js"],
  },
  {
    dimension: "幂等",
    name: "对账用尽后按未送达处理",
    consequence: "查不清的那条会被重发，而它可能已经到了",
    file: src("services/outbox/unknown-result.js"),
    from: '      action: "assume_delivered",\n      resend: false,',
    to: '      action: "assume_delivered",\n      resend: true,',
    tests: ["test/cb9-450-idempotency-reconcile.test.js"],
  },

  // ── 三、位置隐私 ────────────────────────────────────────
  {
    dimension: "位置隐私",
    name: "公开投影里放行经纬度",
    consequence: "精确坐标会跟着位置画像出现在公开面上",
    file: src("services/location/location-profile.js"),
    from: "function publicProjection(",
    to: "function publicProjection_unused(",
    tests: ["test/cb9-220-location-profile.test.js"],
    // 改名会让引用它的地方直接报错——这一刀验的是「有没有人真的在用它」，
    // 而不是它内部判得对不对。判得对不对由下面那刀验。
  },
  {
    dimension: "位置隐私",
    name: "只查解构之后的对象，不查原始输入",
    consequence: "调用方多带的 latitude 在解构那一刻就没了，守卫查了个空气",
    file: src("services/location/timezone-signals.js"),
    from: "function safeObservation(raw = {}) {",
    to: "function safeObservation({ source, timezone, city, country } = {}) {\n  const raw = { source, timezone, city, country };",
    tests: ["test/cb9-210-timezone-signals.test.js"],
  },
  {
    dimension: "位置隐私",
    name: "出网隐私闸从唯一出口上摘掉",
    consequence: "微信 ID、绝对路径、内部会话 ID 会原样出现在公开接口的响应里",
    file: src("services/portal/portal-server.js"),
    from: "      assertPublicEgress(payload, { surface });",
    to: "      /* mutation: gate removed */;",
    tests: ["test/cb9-520-public-egress.test.js"],
  },

  // ── 四、Status 新鲜度 ───────────────────────────────────
  {
    dimension: "Status 新鲜度",
    name: "没有 live receipt 时报健康",
    consequence: "刚部署完、一次都没跑过的系统整片显示绿色——配置性伪绿",
    file: src("services/status/parity-freshness.js"),
    from: '    return build("UNKNOWN", "no_live_receipt", { success, failure, nowMs });',
    to: '    return build("HEALTHY", "no_live_receipt", { success, failure, nowMs });',
    tests: ["test/cb9-500-parity-freshness.test.js", "test/cb9-510-status-vertical-matrix.test.js"],
  },
  {
    dimension: "Status 新鲜度",
    name: "过期的成功也算健康",
    consequence: "一条昨天好过、今天已经断了的路会一直显示绿色",
    file: src("services/status/parity-freshness.js"),
    from: "  if (nowMs - success <= freshMs) {",
    to: "  if (true) {",
    tests: ["test/cb9-500-parity-freshness.test.js"],
  },
  {
    dimension: "Status 新鲜度",
    name: "最近的失败被紧接着的成功抹掉",
    consequence: "抖动被藏起来——「有时候不行」在面板上永远是绿的",
    file: src("services/status/parity-freshness.js"),
    from: "  if (failure !== null && nowMs - failure <= failureStickyMs\n    && (success === null || failure >= success)) {",
    to: "  if (failure !== null && nowMs - failure <= failureStickyMs && success === null) {",
    tests: ["test/cb9-500-parity-freshness.test.js"],
  },
  {
    dimension: "Status 新鲜度",
    name: "量不到的资源当成量到了 0",
    consequence: "磁盘读不出来时显示「资源充裕」，而实际是我们瞎了",
    file: src("services/status/vertical-sections.js"),
    from: "    (value) => value !== null && value !== undefined && Number.isFinite(Number(value)),",
    to: "    (value) => Number.isFinite(Number(value)),",
    tests: ["test/cb9-510-status-vertical-matrix.test.js"],
  },
]);

function runTests(tests) {
  const result = spawnSync("node", ["--test", ...tests], {
    cwd: APP, encoding: "utf8", timeout: 300_000,
  });
  return result.status === 0;
}

function main() {
  const jsonIndex = process.argv.indexOf("--json");
  const jsonOut = jsonIndex >= 0 ? process.argv[jsonIndex + 1] : null;

  // 先确认基线是绿的。基线红的话，后面每一刀都会"红"，而那不说明任何问题。
  const allTests = [...new Set(MUTATIONS.flatMap((m) => m.tests))].sort();
  process.stdout.write("基线…");
  if (!runTests(allTests)) {
    process.stdout.write(" 不是绿的，停。\n");
    process.exit(1);
  }
  process.stdout.write(" 0 红\n\n");

  const rows = [];
  let survived = 0;
  for (const mutation of MUTATIONS) {
    const original = fs.readFileSync(mutation.file, "utf8");
    const occurrences = original.split(mutation.from).length - 1;
    if (occurrences !== 1) {
      // 锚点找不到或者不唯一 = 这个脚本已经和代码脱节了。
      // **算失败，不算跳过**：一个悄悄不再注入任何东西的变异测试，
      // 比没有变异测试更糟——它每次都报全红。
      rows.push({
        dimension: mutation.dimension,
        mutation: mutation.name,
        consequence: mutation.consequence,
        result: "锚点失效",
        detail: `命中 ${occurrences} 次，期望 1 次`,
      });
      survived += 1;
      process.stdout.write(`⚠ 锚点失效  [${mutation.dimension}] ${mutation.name}\n`);
      continue;
    }
    let turnedRed;
    try {
      fs.writeFileSync(mutation.file, original.replace(mutation.from, mutation.to));
      turnedRed = !runTests(mutation.tests);
    } finally {
      // finally 而不是顺序执行：中间抛了异常也必须把源码放回去。
      // 放不回去的话，工作树里留着一份被改坏的代码，而它看起来是正常的。
      fs.writeFileSync(mutation.file, original);
    }
    if (!turnedRed) {
      survived += 1;
    }
    rows.push({
      dimension: mutation.dimension,
      mutation: mutation.name,
      consequence: mutation.consequence,
      file: path.relative(APP, mutation.file),
      tests: mutation.tests,
      result: turnedRed ? "转红" : "存活",
    });
    process.stdout.write(
      `${turnedRed ? "✓ 转红" : "✗ 存活"}  [${mutation.dimension}] ${mutation.name}\n`,
    );
  }

  // 四个维度每个至少一刀——AC-036 的字面要求。
  const byDimension = {};
  for (const row of rows) {
    byDimension[row.dimension] = (byDimension[row.dimension] || 0) + 1;
  }
  const required = ["模式隔离", "幂等", "位置隐私", "Status 新鲜度"];
  const missing = required.filter((name) => !byDimension[name]);

  const report = {
    acceptance: "AC-036",
    requirement: "NFR-006",
    node: "CB9-600",
    baseline_red: 0,
    total: rows.length,
    turned_red: rows.filter((row) => row.result === "转红").length,
    survived,
    dimensions: byDimension,
    missing_dimensions: missing,
    mutations: rows,
  };
  if (jsonOut) {
    fs.mkdirSync(path.dirname(jsonOut), { recursive: true });
    fs.writeFileSync(jsonOut, `${JSON.stringify(report, null, 2)}\n`);
  }
  process.stdout.write(
    `\n${report.turned_red}/${report.total} 转红，维度 ${Object.keys(byDimension).join(" / ")}\n`,
  );
  if (missing.length > 0) {
    process.stdout.write(`AC-036 要求的维度缺了：${missing.join("、")}\n`);
  }
  process.exit(survived === 0 && missing.length === 0 ? 0 : 1);
}

if (require.main === module) {
  main();
}

module.exports = { MUTATIONS };
