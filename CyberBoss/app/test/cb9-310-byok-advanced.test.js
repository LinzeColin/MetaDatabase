"use strict";

// CB9-310 BYOK 移到高级自选，主流程去技术词（AC-008）
//
//   AC-008 BYOK 入口默认不可见，仅在高级设置主动展开后出现；关闭后不影响会话。
//
// 改之前，设置页**一打开就是** BYOK：第一眼是「连接你自己的 AI」加一个「粘贴
// 你的密钥」输入框。对一个刚扫完码的人，这等于告诉他「你还差一步才能用」——
// 而他其实已经能用了。FR-008 的原话：「BYOK 仅在高级设置中由用户主动展开，
// 不影响主流程和普通功能。」

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const { MESSAGES } = require("../src/services/ops/novice-presenter");

const PORTAL = fs.readFileSync(
  path.join(__dirname, "..", "templates", "setup-portal.html"), "utf8",
);

function sectionBetween(html, startMarker, endMarker) {
  const start = html.indexOf(startMarker);
  const end = html.indexOf(endMarker, start);
  assert.ok(start !== -1 && end !== -1, `找不到 ${startMarker} … ${endMarker}`);
  return html.slice(start, end);
}

// ── AC-008 默认不可见 ─────────────────────────────────────

test("AC-008 BYOK 整段在折叠的高级设置里", () => {
  const advanced = sectionBetween(PORTAL, '<details id="advanced">', "</details>");
  // 服务选择、密钥输入框、保存按钮，一个都不能留在外面。
  for (const piece of ['id="provider"', 'id="apikey"', 'id="save-provider"', "view-provider"]) {
    assert.ok(advanced.includes(piece), `BYOK 的 ${piece} 露在高级设置外面`);
  }
});

test("AC-008 details 默认折叠——没有 open 属性", () => {
  // 用 <details> 而不是 JS 控制显隐是有意的：浏览器原生就是收起来的，不需要
  // 脚本，也不会「先闪一下再收起来」。脚本控制的版本在 JS 加载慢或被 CSP 挡住
  // 的时候会把密钥输入框直接摊开——而那正是最不该出问题的时刻。
  assert.doesNotMatch(PORTAL, /<details id="advanced"[^>]*\sopen/,
    "高级设置默认是展开的");
  assert.match(PORTAL, /<details id="advanced">\s*<summary>高级设置<\/summary>/);
});

test("AC-008 页面默认落地的不是 BYOK", () => {
  // view-ready 必须排在 details 前面：DOM 顺序就是用户的阅读顺序。
  const readyAt = PORTAL.indexOf('id="view-ready"');
  const advancedAt = PORTAL.indexOf('<details id="advanced">');
  assert.ok(readyAt !== -1, "没有落地屏");
  assert.ok(readyAt < advancedAt, "落地屏排在了高级设置后面");
  // 落地屏第一句就是「已经可以用了」，不是「还差一步」。
  const ready = sectionBetween(PORTAL, 'id="view-ready"', "</section>");
  assert.match(ready, /已经可以用了/);
  // 落地屏上不许出现任何 BYOK 字样。
  for (const term of ["密钥", "apikey", "provider", "OpenAI", "DeepSeek", "Anthropic"]) {
    assert.ok(!ready.includes(term), `落地屏上出现了 ${term}`);
  }
});

test("AC-008 落地屏不是死的——上面那个按钮真的绑了处理器", () => {
  // 一个点了没反应的按钮比没有按钮更糟。
  assert.match(PORTAL, /id="go-import"/);
  assert.match(PORTAL, /goImport\.addEventListener\("click"/);
});

test("AC-008 只有用户主动来找 BYOK 时才展开", () => {
  // 从微信回「连接我的AI」会带 ?p=provider 过来——那是一次**主动**请求，
  // 展开是对的。没带这个参数就保持折叠。
  const script = sectionBetween(PORTAL, "var views = { provider", "var csrf");
  assert.match(script, /purpose === "provider"/);
  assert.match(script, /advanced\.open = true/);
  // 而且展开只发生在这一个分支里：全局无条件展开就等于没折叠。
  assert.equal((PORTAL.match(/\.open = true/g) || []).length, 1,
    "有不止一处会展开高级设置");
});

// ── AC-008 关掉不影响会话 ─────────────────────────────────

test("AC-008 跳过 BYOK 不做任何写操作——只是换一句提示", () => {
  const skip = sectionBetween(PORTAL, 'var skipButton = document.getElementById("skip-provider")',
    "// 导入：先把清单送去预检");
  // 跳过就是跳过：不发请求、不改会话、不跳视图。
  for (const call of ["fetch(", "show(", "location", "history."]) {
    assert.ok(!skip.includes(call), `「先跳过」这个按钮做了 ${call}`);
  }
  assert.match(skip, /随时可以回微信/);
});

test("AC-008 保存 BYOK 失败不该把人踢出会话", () => {
  // 「不影响会话」的另一半：BYOK 出错时页面回到错误屏，但会话本身还在，
  // 用户回微信继续说话照样能用。所以错误处理里不许有登出/清 cookie 这类动作。
  const save = sectionBetween(PORTAL, 'var saveButton = document.getElementById("save-provider")',
    'var goImport');
  for (const kill of ["logout", "document.cookie", "location.reload", "location.href"]) {
    assert.ok(!save.includes(kill), `保存 BYOK 的路径上有 ${kill}`);
  }
});

// ── AC-008 主流程不推销 BYOK ──────────────────────────────

test("AC-008 开通完那句话不再推销「连接自己的 AI」", () => {
  // 写在这里的后果是：每个刚开通的人第一眼就以为自己还差一步，而他其实已经
  // 能用了。想接自己那套的人回「设置」照样找得到，它在高级设置里。
  const home = MESSAGES.home.text;
  assert.match(home, /已经可以用了/);
  assert.ok(!home.includes("连接自己的 AI"), `主流程还在推销 BYOK：${home}`);
  assert.ok(!home.includes("密钥"), home);
});

test("AC-008 BYOK 相关的提示只出现在需要它的分支上", () => {
  // provider_missing / provider_invalid 是**已经**用了 BYOK 的人才会看到的。
  // 它们提到「连接我的AI」是对的；主流程的 welcome / consent / home 不该提。
  for (const key of ["welcome", "consent", "home"]) {
    const text = MESSAGES[key].text;
    assert.ok(!/连接我的AI|连接自己的 AI/.test(text),
      `${key} 在主流程里推销 BYOK：${text}`);
  }
  // 反面：需要它的那两条必须还在，否则用户卡住了没人告诉他怎么修。
  assert.match(MESSAGES.provider_missing.text, /连接我的AI/);
  assert.match(MESSAGES.provider_invalid.text, /连接我的AI/);
});

test("AC-008 微信侧仍然认得「连接我的AI」这条主动指令", () => {
  // 高级不等于藏起来找不到。用户主动说这四个字，必须还能到那一页。
  const map = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "commands", "novice-command-map.js"), "utf8");
  assert.match(map, /"portal\.provider":/);
  assert.match(map, /连接我的ai/);
});
