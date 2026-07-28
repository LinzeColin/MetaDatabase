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
  for (const phrase of ["微信读书同步", "完整核对全部数据", "下载已同步数据（JSON）", "官方可导出正文", "书签只有官方计数", "Notion", "Obsidian", "GitHub", "Google Drive", "不知道怎么选？", "选择文件夹", "导入任务已建立"]) assert.ok(ui.includes(phrase), phrase);
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

test("画像、官方统计、笔记活动、推荐、跨设备和隐私控制都在账户 UI 中可见", () => {
  for (const phrase of ["阅读偏好，已经整合到首页", "微信读书官方阅读统计", "官方阅读统计", "笔记活动", "潜在推荐", "在微信读书打开", "行为分析", "个性化推荐", "跨设备", "永久删除账户", "导出我的全部数据", "下载微信读书数据（JSON）"]) assert.ok(ui.includes(phrase), phrase);
  assert.equal(ui.includes("近 90 天阅读热度"), false, "笔记事件不得再被标为阅读热度");
});

test("笔记页按真实字段实时筛选，并只对当前显示结果下载或交接 ChatGPT", () => {
  for (const phrase of ["模糊搜索", "书籍", "作者", "开始时间", "结束时间", "实时筛选", "打包下载当前结果", "带当前结果问 ChatGPT", "带这条笔记问 ChatGPT", "官方当前返回的真实事件时间"]) assert.ok(ui.includes(phrase), phrase);
  assert.ok(ui.includes("data-note-filter"));
  assert.ok(ui.includes("renderAccountNotesChatGPTContext"));
  assert.ok(ui.includes("CHATGPT_HANDOFF_URL"));
  assert.ok(api.includes("/notes/export"));
  assert.equal(ui.includes("web/bookDetail"), false, "不得用书籍 ID 伪造微信读书详情地址");
});

test("UI UX Pro Max 关键可访问性合同：44px 触控、焦点、减弱动态和 320px", () => {
  assert.match(css, /min-height:\s*44px/u);
  assert.match(css, /:focus-visible/u);
  assert.match(css, /prefers-reduced-motion/u);
  assert.match(css, /max-width:\s*380px/u);
  assert.ok(ui.includes('aria-live="polite"'));
  assert.ok(ui.includes('role="switch"'));
});
