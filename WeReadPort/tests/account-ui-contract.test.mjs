import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const files = await Promise.all([
  readFile(new URL("../src/ui/account-platform.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/account-api.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/obsidian-import.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/styles.css", import.meta.url), "utf8"),
]);
const [ui, api, obsidian, css] = files;

test("首屏提供密钥、邮箱密码及 Google/GitHub/Notion 三类非技术登录入口", () => {
  for (const phrase of ["微信读书密钥", "邮箱和密码", "Google", "GitHub", "Notion", "创建账户", "登录"]) assert.ok(ui.includes(phrase), phrase);
  assert.ok(api.includes("/auth/register/password"));
  assert.ok(api.includes("/auth/register/weread"));
  assert.ok(api.includes("/oauth/"));
});

test("四平台导入均使用连接、选择、预览/确认和进度式新手路径", () => {
  for (const phrase of ["微信读书同步", "完整核对全部数据", "下载已同步数据（JSON）", "Notion", "Obsidian", "GitHub", "Google Drive", "不知道怎么选？", "选择文件夹", "导入任务已建立"]) assert.ok(ui.includes(phrase), phrase);
  assert.ok(obsidian.includes("webkitRelativePath"));
  assert.ok(obsidian.includes("ZIP"));
  assert.ok(api.includes("/weread/export"));
  assert.ok(api.includes('cache: "no-store"'));
  assert.match(ui, /runWeReadSync\(content, \{ forceFull: true, preserveView: true \}\)/u);
  assert.match(ui, /async function runWeReadSync\(content, \{ automatic = false, forceFull = false, preserveView = false \} = \{\}\)/u);
  assert.match(ui, /if \(!preserveView\) state\.view = "notes";/u);
});

test("任意成功登录、OAuth 回跳或首次恢复会自动同步微信读书", () => {
  assert.match(ui, /function syncWeReadAfterLogin\(root, \{ force = false \} = \{\}\)/u);
  assert.equal((ui.match(/if \(result\) void syncWeReadAfterLogin\(document, \{ force: true \}\);/gu) || []).length, 2);
  assert.match(ui, /void syncWeReadAfterLogin\(root, \{ force: oauthReturned \}\)/u);
  assert.ok(ui.includes("已登录，正在后台检查微信读书最新变化…"));
  assert.ok(api.includes("wereadSync(mode = \"auto\")"));
  assert.ok(ui.includes("真实事件时间"));
});

test("画像、热度、推荐、跨设备和隐私控制都在账户 UI 中可见", () => {
  for (const phrase of ["阅读偏好，已经整合到首页", "阅读热度", "潜在推荐", "在微信读书打开", "行为分析", "个性化推荐", "跨设备", "永久删除账户", "导出我的全部数据", "下载微信读书数据（JSON）"]) assert.ok(ui.includes(phrase), phrase);
});

test("UI UX Pro Max 关键可访问性合同：44px 触控、焦点、减弱动态和 320px", () => {
  assert.match(css, /min-height:\s*44px/u);
  assert.match(css, /:focus-visible/u);
  assert.match(css, /prefers-reduced-motion/u);
  assert.match(css, /max-width:\s*380px/u);
  assert.ok(ui.includes('aria-live="polite"'));
  assert.ok(ui.includes('role="switch"'));
});
