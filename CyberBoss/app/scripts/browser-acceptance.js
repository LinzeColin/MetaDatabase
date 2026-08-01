"use strict";

// CB9-340 真实浏览器验收（AC-030 / AC-037 / AC-042 的实测面）。
//
// 这个脚本**不进单元测试套件**：它要一个真的浏览器，而套件必须能在没有浏览器
// 的机器上跑完。它由 CB9-340 手动执行并把结果写进证据，缺浏览器时该节点如实
// 标 NOT_RUN——不是用一份静态扫描冒充实测。
//
// 量的是三样，每一样都必须是**渲染之后**的真实数字：
//
//   横向溢出   —— documentElement.scrollWidth - clientWidth。CSS 规则对不等于
//                  没溢出：某一段具体内容照样能把容器撑破。
//   触控区     —— 每个可点元素 getBoundingClientRect() 的实际高宽。
//                  「CSS 里写了 min-height:44px」证明不了按钮真的是 44px——
//                  一个 display:inline 的 <a> 上 min-height 根本不生效。
//   权限弹窗   —— 挂上 geolocation / permissions / getUserMedia 的钩子，
//                  页面跑完之后看有没有人碰过（AC-042）。
//
// 用法：node scripts/browser-acceptance.js [--json]

const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const TEMPLATES = path.join(__dirname, "..", "templates");
const PAGES = ["home.html", "join.html", "me.html", "setup-portal.html", "dashboard.html", "ops-wechat.html"];

// AC-030 点名的两个视口。
const VIEWPORTS = [
  { name: "mobile-375x812", width: 375, height: 812, deviceScaleFactor: 3, isMobile: true },
  { name: "desktop-1280x720", width: 1280, height: 720, deviceScaleFactor: 1, isMobile: false },
];

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// 页面在真实服务下拿到的是替换过占位符的 HTML。直接读模板会把
// __CSP_NONCE__ 原样送进浏览器，内联样式全被 CSP 拦掉——量出来的就不是真实布局。
function renderedHtml(name) {
  return fs.readFileSync(path.join(TEMPLATES, name), "utf8")
    .replaceAll("__CSP_NONCE__", "acceptancenonce")
    .replaceAll("__USAGE_PERCENT__", "42");
}

// 起一个本地服务而不是用 file://：file:// 下 CSP、fetch 和相对路径的行为都和
// 线上不一样，量出来的东西就不能代表线上。
function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const name = decodeURIComponent((request.url || "/").split("?")[0]).replace(/^\//, "");
      if (!PAGES.includes(name)) {
        response.writeHead(404).end("not found");
        return;
      }
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      response.end(renderedHtml(name));
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

// 在页面里跑的测量。返回纯数据，判定留在 Node 侧——把断言写进页面脚本的话，
// 失败时只能看到 false，看不到是哪个元素多宽。
const MEASURE = `(() => {
  const doc = document.documentElement;
  const overflow = doc.scrollWidth - doc.clientWidth;
  const small = [];
  const selector = 'button, a, input:not([type=hidden]), select, textarea, [role=button], summary';
  for (const el of document.querySelectorAll(selector)) {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    // 看不见的元素不算：折叠起来的高级设置里那些是有意隐藏的。
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    if (box.width === 0 && box.height === 0) continue;
    if (box.height < 44 || box.width < 44) {
      small.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        text: (el.textContent || '').trim().slice(0, 16),
        w: Math.round(box.width * 10) / 10,
        h: Math.round(box.height * 10) / 10,
        display: style.display,
      });
    }
  }
  // 溢出到底是谁造成的。只报一个总数的话，修的时候还得自己去找。
  const wide = [];
  for (const el of document.querySelectorAll('*')) {
    const box = el.getBoundingClientRect();
    if (box.right > doc.clientWidth + 1) {
      wide.push({ tag: el.tagName.toLowerCase(), id: el.id || '', cls: (el.className || '').toString().slice(0, 24), right: Math.round(box.right) });
    }
  }
  return {
    overflow,
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    smallTargets: small,
    overflowingElements: wide.slice(0, 8),
    permissionCalls: window.__permissionCalls || [],
    h1Count: document.querySelectorAll('h1').length,
    title: document.title,
  };
})()`;

// 权限钩子必须在页面脚本**之前**装上，否则页面在我们装钩子之前就弹过框了。
const PERMISSION_HOOK = `
  window.__permissionCalls = [];
  const record = (name) => window.__permissionCalls.push(name);
  try {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      get() { record('navigator.geolocation'); return {
        getCurrentPosition: () => record('getCurrentPosition'),
        watchPosition: () => record('watchPosition'),
      }; },
    });
  } catch (_) {}
  try {
    if (navigator.permissions) {
      const original = navigator.permissions.query.bind(navigator.permissions);
      navigator.permissions.query = (...args) => { record('permissions.query'); return original(...args); };
    }
  } catch (_) {}
  try {
    if (navigator.mediaDevices) {
      navigator.mediaDevices.getUserMedia = () => { record('getUserMedia'); return Promise.reject(new Error('blocked')); };
    }
  } catch (_) {}
  try {
    const originalNotification = window.Notification;
    if (originalNotification) {
      originalNotification.requestPermission = () => { record('Notification.requestPermission'); return Promise.resolve('denied'); };
    }
  } catch (_) {}
`;

async function main() {
  if (!fs.existsSync(CHROME)) {
    console.error(`NOT_RUN：这台机器上找不到 Chrome（${CHROME}）。`);
    process.exit(2);
  }
  const { chromium } = require("playwright-core");
  const { server, port } = await startServer();
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const results = [];
  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: viewport.deviceScaleFactor,
        isMobile: viewport.isMobile,
        hasTouch: viewport.isMobile,
        locale: "zh-CN",
        // AC-042：定位权限**拒绝**。页面必须照样能用。
        permissions: [],
        geolocation: undefined,
      });
      await context.addInitScript(PERMISSION_HOOK);
      const page = await context.newPage();
      const consoleErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text().slice(0, 160));
      });
      page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${String(error.message).slice(0, 160)}`));

      for (const name of PAGES) {
        const startedAt = Date.now();
        await page.goto(`http://127.0.0.1:${port}/${name}`, { waitUntil: "load", timeout: 15_000 });
        // 让页面自己的脚本跑一轮（加入页会去要二维码，会失败，那正是我们要看的：
        // 接口挂了页面也不能崩）。
        await page.waitForTimeout(400);
        const measured = await page.evaluate(MEASURE);
        results.push({
          viewport: viewport.name,
          page: name,
          loadMs: Date.now() - startedAt,
          ...measured,
          consoleErrors: [...consoleErrors],
        });
        consoleErrors.length = 0;
      }
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  const failures = [];
  for (const row of results) {
    if (row.overflow > 0) {
      failures.push(`${row.viewport} / ${row.page}: 横向溢出 ${row.overflow}px（${JSON.stringify(row.overflowingElements)}）`);
    }
    if (row.smallTargets.length) {
      failures.push(`${row.viewport} / ${row.page}: ${row.smallTargets.length} 个控件小于 44px ${JSON.stringify(row.smallTargets)}`);
    }
    if (row.permissionCalls.length) {
      failures.push(`${row.viewport} / ${row.page}: 碰了权限接口 ${row.permissionCalls.join(", ")}`);
    }
    if (row.h1Count !== 1) {
      failures.push(`${row.viewport} / ${row.page}: h1 有 ${row.h1Count} 个`);
    }
  }

  const report = {
    chrome: CHROME,
    chromeVersion: null,
    viewports: VIEWPORTS.map((v) => v.name),
    pages: PAGES,
    results,
    failures,
    verdict: failures.length === 0 ? "PASS" : "FAIL",
  };
  if (process.argv.includes("--json")) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    for (const row of results) {
      const flag = row.overflow > 0 || row.smallTargets.length || row.permissionCalls.length ? "✖" : "✔";
      console.log(`${flag} ${row.viewport.padEnd(18)} ${row.page.padEnd(20)} 溢出=${row.overflow}px 小控件=${row.smallTargets.length} 权限调用=${row.permissionCalls.length} 加载=${row.loadMs}ms`);
    }
    if (failures.length) {
      console.log("\n失败明细：");
      for (const line of failures) console.log("  " + line);
    }
    console.log(`\n结论：${report.verdict}`);
  }
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => {
  console.error("NOT_RUN：", error.message);
  process.exit(2);
});
