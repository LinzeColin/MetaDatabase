import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const files = await Promise.all([
  readFile(new URL("../src/ui/account-platform.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/account-api.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/obsidian-import.js", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/styles.css", import.meta.url), "utf8"),
  readFile(new URL("../src/ui/admin-app.js", import.meta.url), "utf8"),
  readFile(new URL("../admin.html", import.meta.url), "utf8"),
]);
const [ui, api, obsidian, css, adminUi, adminHtml] = files;

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
  assert.ok(api.includes("/weread/sync/jobs/"));
  assert.ok(api.includes('cache: "no-store"'));
  assert.match(ui, /runWeReadSync\(content, \{ forceFull: true, preserveView: true \}\)/u);
  assert.match(ui, /async function runWeReadSync\(content, \{ automatic = false, forceFull = false, preserveView = false \} = \{\}\)/u);
  assert.match(ui, /async function waitForWeReadSync\(jobId\)/u);
  assert.ok(ui.includes("已建立后台微信读书同步任务"));
  assert.match(ui, /if \(!automatic && !preserveView\) state\.view = "notes";/u);
});

test("任意成功登录、OAuth 回跳或首次恢复会自动同步微信读书", () => {
  assert.match(ui, /function syncWeReadAfterLogin\(root, \{ force = false \} = \{\}\)/u);
  assert.equal((ui.match(/if \(result\) void syncWeReadAfterLogin\(document, \{ force: true \}\);/gu) || []).length, 2);
  assert.match(ui, /void syncWeReadAfterLogin\(root, \{ force: oauthReturned \}\)/u);
  assert.ok(ui.includes("已建立后台微信读书同步任务；可继续浏览，完成后会自动刷新数据。"));
  assert.ok(api.includes("wereadSync(mode = \"auto\")"));
  assert.ok(api.includes("wereadSyncJob(id)"));
  assert.match(ui, /void observeWeReadSync\(job\.id, \{ automatic, preserveView \}\);/u);
  assert.ok(ui.includes("真实事件时间"));
  assert.match(ui, /async function refreshDerivedAccountState\(\)/u);
  assert.match(ui, /Promise\.all\(\[api\.profile\(\), api\.notes\(\), api\.analytics\(\)\]\)/u);
  assert.ok(ui.includes("await refreshDerivedAccountState()"));
  assert.ok((ui.match(/await refreshDerivedAccountState\(\);/gu) || []).length >= 4, "微信读书、导入、手动保存和删除都必须刷新下游快照");
});

test("画像、官方统计、笔记活动、推荐、跨设备和隐私控制都在账户 UI 中可见", () => {
  for (const phrase of ["阅读偏好，已经整合到首页", "微信读书官方阅读统计", "官方阅读统计", "微信读书官方阅读快照", "阅读进展", "类别分布", "本次来源同步于", "笔记活动", "潜在推荐", "在微信读书打开", "复制书名", "复制作者", "行为分析", "个性化推荐", "跨设备", "永久删除账户", "导出我的全部数据", "下载微信读书数据（JSON）"]) assert.ok(ui.includes(phrase), phrase);
  assert.equal(ui.includes("近 90 天阅读热度"), false, "笔记事件不得再被标为阅读热度");
  assert.equal(ui.includes("<h2>来源分布</h2>"), false, "可视化应显示类别而非来源分布");
  assert.match(ui, /import \{ gsap \} from "gsap";/u);
  assert.match(ui, /gsap\.matchMedia\(\)/u);
  assert.match(ui, /prefers-reduced-motion: reduce/u);
  assert.match(ui, /prefers-reduced-motion: no-preference/u);
  assert.match(ui, /compactCategoryDistribution/u);
  assert.match(ui, /noteTrendChart/u);
  assert.match(ui, /readingProgressChart/u);
  assert.match(ui, /copyRecommendationValue/u);
});

test("笔记页按真实字段筛选，并按书籍、作者或时间归档后只携带单条笔记问 AI", () => {
  for (const phrase of ["模糊搜索", "书籍", "作者", "开始时间", "结束时间", "实时筛选", "打包下载当前结果", "书籍分类", "作者分类", "时间分类", "note-archive-heading", "去 AI 问询", "选择一条笔记去 AI 问询", "官方当前返回的真实事件时间", "点击笔记才会按需解密并显示完整正文", "查看正文", "当前视图操作", "缩小当前阅读档案", "选择一本书生成 Book-to-Skill", "我的 Book-to-Skill", "Book-to-Skill 预览"]) assert.ok(ui.includes(phrase), phrase);
  assert.ok(ui.includes("data-note-filter"));
  assert.ok(ui.includes("notes-workbench"));
  assert.ok(ui.includes("data-note-open"));
  assert.ok(ui.includes("renderSingleNoteAiInquiry"));
  assert.ok(ui.includes("copyTextToClipboard"));
  assert.ok(ui.includes("AI 问询"));
  for (const phrase of ["发起问询", "我的风格", "问询记录", "AI_INQUIRY_PROVIDERS", "AI_INQUIRY_STYLES", "DEFAULT_AI_INQUIRY_PROVIDER_ID", "DEFAULT_AI_INQUIRY_STYLE_ID"]) assert.ok(ui.includes(phrase), phrase);
  assert.ok(api.includes("/notes/export"));
  assert.ok(api.includes("/book-skills"));
  assert.ok(api.includes("/ai/preferences"));
  assert.ok(api.includes("/ai/inquiries"));
  assert.equal(ui.includes("admin.weread.linzezhang.com"), false, "普通用户页面不得展示管理域");
  assert.equal(ui.includes("管理员控制台"), false, "普通用户页面不得展示管理员功能");
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

test("管理员界面独立构建，普通用户页面不含管理导航或管理数据展示", () => {
  assert.ok(adminHtml.includes("阅迁 Admin"));
  for (const phrase of ["不可变账户白名单", "登录后直接查看管理数据", "Promise.allSettled", "session/handoff", "管理员控制台", "adminPrompts", "adminNote", "adminBookSkills", "adminSecurity", "Book-to-Skill", "登录与安全", "DIRECT_LIST_LIMIT"]) assert.ok(adminUi.includes(phrase), phrase);
  assert.equal(adminUi.includes("读取并审计"), false);
  assert.equal(adminUi.includes("查看用途"), false);
  assert.equal(adminUi.includes("近期身份验证"), false);
  assert.equal(ui.includes("admin-app.js"), false);
  assert.equal(ui.includes("用户资料"), false);
  assert.equal(ui.includes("审计日志"), false);
});
