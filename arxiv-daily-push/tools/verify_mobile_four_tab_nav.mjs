#!/usr/bin/env node
// S4.2 载荷型验证器：按 01→02 顺序物化完整 Worker，执行真实 default.fetch 页面，
// 再用 system Chrome/CDP 验证六主题移动四标签、桌面三导航、边界与独立破坏负控。
// 不联网、不写产品数据、不修改 canonical Worker。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import url from 'node:url';
import net from 'node:net';
import { createHash } from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const LIVE_WORKER = path.join(ROOT, 'deploy', 'cloudflare', 'worker_cloud.js');
const PATCH_01 = path.join(ROOT, 'deploy', 'cloudflare', 'v1_2', 'patches', '01_human_language_fail_closed.patch');
const PATCH_02 = path.join(ROOT, 'deploy', 'cloudflare', 'v1_2', 'patches', '02_mobile_four_tab_nav.patch');
const EXPECTED = {
  liveFileSha256: '319178f05490588701c10c40fd8dad653d4b58e35c7acbfe1224f7282a20a196',
  patch01Sha256: '3f323220cad779d353e0b653d6edfdbd94292433aa8306f9045f9badcda8e9cf',
  patch01Blob: '9ff676970c20369ca562aa8a9639016fa08bb1c7',
  candidateBuild: 'a98b4c957f30',
  candidateSourceSha256: 'a98b4c957f304600da1c95263c4232719ffaebf52cc3ff4bc9e3fd1910ac79c4',
  candidateFileSha256: '39f8a8d82aec8f97e83d595f95ba52ae062191b801632661922077c9632b356b',
  candidateBlob: '461fb1a225c0a8826cf0647181a9969a53618c3a',
};
const THEMES = ['warm', 'minimal', 'fresh', 'techno', 'cosmos', 'forest'];
const THEME_NAV = {
  warm: 'nav-side',
  minimal: 'nav-top',
  fresh: 'nav-top',
  techno: 'nav-dock',
  cosmos: 'nav-dock',
  forest: 'nav-side',
};
const MOBILE_LABELS = ['今天', '队列', '雷达', '系统'];
const MOBILE_HREFS = ['/', '/review', '/radar', '/system'];
const DESKTOP_LABELS = ['今天', '复习', '前沿雷达', '关注', '知识库', '系统'];
const DESKTOP_HREFS = ['/', '/review', '/radar', '/watchlist', '/library', '/system'];
const ACTIVE_ROUTES = [
  ['/', '今天'],
  ['/review', '队列'],
  ['/radar', '雷达'],
  ['/system', '系统'],
];
const sha256 = value => createHash('sha256').update(value).digest('hex');
const fileSha256 = file => sha256(fs.readFileSync(file));
const args = process.argv.slice(2);
const argValue = name => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
};
const externalEvidenceDir = argValue('--evidence-dir');
const requestedChrome = argValue('--chrome');
const workRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'adp-v12-s4-mobile-nav-'));
const workerPath = path.join(workRoot, 'arxiv-daily-push', 'deploy', 'cloudflare', 'worker_cloud.js');
fs.mkdirSync(path.dirname(workerPath), { recursive: true });
fs.copyFileSync(LIVE_WORKER, workerPath);
const failures = [];

function applyPatch(patchFile, label, unidiffZero = false) {
  const result = spawnSync('git', [
    'apply',
    ...(unidiffZero ? ['--unidiff-zero'] : []),
    '--unsafe-paths',
    patchFile,
  ], {
    cwd: workRoot,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(`${label} 无法应用：\n${result.stdout}${result.stderr}`);
  }
}

if (fileSha256(LIVE_WORKER) !== EXPECTED.liveFileSha256) {
  failures.push('canonical Worker 文件 SHA-256 偏离合同');
}
if (fileSha256(PATCH_01) !== EXPECTED.patch01Sha256) {
  failures.push('S4.1 patch SHA-256 偏离已验收值');
}
applyPatch(PATCH_01, 'S4.1 patch');
const patch01Blob = spawnSync('git', ['hash-object', workerPath], { encoding: 'utf8' }).stdout.trim();
if (patch01Blob !== EXPECTED.patch01Blob) failures.push(`S4.1 物化 blob 漂移: ${patch01Blob}`);
applyPatch(PATCH_02, 'S4.2 patch', true);
const source = fs.readFileSync(workerPath, 'utf8');
const candidateFileSha256 = sha256(source);
const candidateBlob = spawnSync('git', ['hash-object', workerPath], { encoding: 'utf8' }).stdout.trim();
if (candidateFileSha256 !== EXPECTED.candidateFileSha256) {
  failures.push(`S4.2 候选文件 SHA-256 漂移: ${candidateFileSha256}`);
}
if (candidateBlob !== EXPECTED.candidateBlob) failures.push(`S4.2 候选 blob 漂移: ${candidateBlob}`);
const stamp = /build_id: '([0-9a-f]{12})', source_sha256: '([0-9a-f]{64})'/.exec(source);
if (!stamp) {
  failures.push('S4.2 候选缺 BUILD stamp');
} else {
  const zeroed = source
    .replace(`build_id: '${stamp[1]}'`, `build_id: '${'0'.repeat(12)}'`)
    .replace(`source_sha256: '${stamp[2]}'`, `source_sha256: '${'0'.repeat(64)}'`);
  const recomputed = sha256(zeroed);
  if (
    stamp[1] !== EXPECTED.candidateBuild
    || stamp[2] !== EXPECTED.candidateSourceSha256
    || stamp[2] !== recomputed
    || stamp[1] !== recomputed.slice(0, 12)
  ) {
    failures.push('S4.2 候选 BUILD stamp 不可复现或未绑定合同值');
  }
}

// 四个 GET 页面走完整 Worker default.fetch。fixture 只返回空读结果，任何写请求均失败。
const fixtureDB = {
  prepare(sql) {
    return {
      sql,
      args: [],
      bind(...values) {
        this.args = values;
        return this;
      },
      async first() {
        if (/SELECT AVG\(/.test(sql)) return { r: null };
        if (/SELECT COUNT\(\*\) n/.test(sql)) return { n: 0 };
        return null;
      },
      async all() {
        return { results: [] };
      },
      async run() {
        throw new Error(`S4.2 browser fixture 禁止写入: ${sql}`);
      },
    };
  },
  async batch(statements) {
    return statements.map(() => ({ results: [] }));
  },
};
const workerModule = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const routeHtml = new Map();
for (const [route] of ACTIVE_ROUTES) {
  const response = await workerModule.default.fetch(
    new Request(`https://s4-mobile-fixture.invalid${route}`),
    { DB: fixtureDB },
  );
  const html = await response.text();
  if (response.status !== 200) failures.push(`真实 Worker route ${route} 返回 ${response.status}`);
  if ((html.match(/aria-label="移动端主导航"/g) || []).length !== 1) {
    failures.push(`真实 Worker route ${route} 未渲染唯一移动主导航`);
  }
  routeHtml.set(route, html);
}

function locateChrome() {
  const candidates = [
    requestedChrome,
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  ].filter(Boolean);
  return candidates.find(candidate => fs.existsSync(candidate)) || null;
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

class CDP {
  constructor(webSocketUrl) {
    this.socket = new WebSocket(webSocketUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', reject, { once: true });
    });
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const waiter = this.pending.get(message.id);
        if (!waiter) return;
        this.pending.delete(message.id);
        if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
        else waiter.resolve(message.result);
        return;
      }
      this.events.push(message);
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async close() {
    if (this.socket.readyState === WebSocket.OPEN) this.socket.close();
  }
}

const metricExpression = `(() => {
  const display = element => element ? getComputedStyle(element).display : null;
  const rect = element => {
    if (!element) return null;
    const value = element.getBoundingClientRect();
    return {x:value.x,y:value.y,width:value.width,height:value.height,top:value.top,bottom:value.bottom};
  };
  const nav = document.querySelector('nav.nav-mobile');
  const links = nav ? [...nav.querySelectorAll(':scope > a')] : [];
  const desktop = [...document.querySelectorAll('nav.nav-top,nav.nav-side,nav.nav-dock')];
  const footer = document.querySelector('footer.receipt');
  return {
    theme: document.documentElement.getAttribute('data-theme'),
    navMode: document.documentElement.getAttribute('data-nav'),
    mobileCount: document.querySelectorAll('nav.nav-mobile').length,
    mobileDisplay: display(nav),
    mobilePosition: nav ? getComputedStyle(nav).position : null,
    mobileRect: rect(nav),
    mobileGridColumns: nav ? getComputedStyle(nav).gridTemplateColumns : null,
    labels: links.map(link => link.textContent.trim()),
    hrefs: links.map(link => link.getAttribute('href')),
    activeLabels: links.filter(link => link.getAttribute('aria-current') === 'page').map(link => link.textContent.trim()),
    linkRects: links.map(rect),
    linkWhiteSpace: links.map(link => getComputedStyle(link).whiteSpace),
    desktop: desktop.map(element => ({
      className: element.className,
      display: display(element),
      rect: rect(element),
      labels: [...element.querySelectorAll(':scope > a')].map(link => link.textContent.trim()),
      hrefs: [...element.querySelectorAll(':scope > a')].map(link => link.getAttribute('href')),
      activeLabels: [...element.querySelectorAll(':scope > a[aria-current="page"]')].map(link => link.textContent.trim()),
    })),
    viewport: {width: innerWidth,height: innerHeight},
    scroll: {
      htmlWidth: document.documentElement.scrollWidth,
      htmlClientWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth,
      bodyClientWidth: document.body.clientWidth,
    },
    footerPaddingBottom: footer ? parseFloat(getComputedStyle(footer).paddingBottom) : null,
  };
})()`;

function same(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

function mobileViolations(metric, expectedActive = '今天') {
  const out = [];
  if (metric.mobileCount !== 1) out.push(`mobile nav count=${metric.mobileCount}`);
  if (metric.mobileDisplay !== 'grid') out.push(`mobile display=${metric.mobileDisplay}`);
  if (metric.mobilePosition !== 'fixed') out.push(`mobile position=${metric.mobilePosition}`);
  if (!same(metric.labels, MOBILE_LABELS)) out.push(`mobile labels=${JSON.stringify(metric.labels)}`);
  if (!same(metric.hrefs, MOBILE_HREFS)) out.push(`mobile hrefs=${JSON.stringify(metric.hrefs)}`);
  if (!same(metric.activeLabels, [expectedActive])) out.push(`mobile active=${JSON.stringify(metric.activeLabels)}`);
  if (metric.desktop.some(nav => nav.display !== 'none')) out.push('mobile viewport 暴露 desktop nav');
  if (metric.linkRects.length !== 4 || metric.linkRects.some(rect => !rect || rect.height < 44)) {
    out.push(`mobile click heights=${JSON.stringify(metric.linkRects.map(rect => rect && rect.height))}`);
  }
  const widths = metric.linkRects.map(rect => rect && rect.width);
  if (widths.length !== 4 || widths.some(width => width == null) || Math.max(...widths) - Math.min(...widths) > 1) {
    out.push(`mobile columns not equal=${JSON.stringify(widths)}`);
  }
  if (metric.linkWhiteSpace.some(value => value !== 'nowrap')) out.push('mobile label 可换行');
  if (
    metric.scroll.htmlWidth !== metric.scroll.htmlClientWidth
    || metric.scroll.bodyWidth !== metric.scroll.bodyClientWidth
  ) {
    out.push(`horizontal overflow=${JSON.stringify(metric.scroll)}`);
  }
  if (
    !metric.mobileRect
    || metric.mobileRect.width < metric.viewport.width - 1
    || Math.abs(metric.mobileRect.bottom - metric.viewport.height) > 1
  ) {
    out.push(`mobile nav 未贴合 viewport=${JSON.stringify(metric.mobileRect)}`);
  }
  if (
    metric.footerPaddingBottom == null
    || !metric.mobileRect
    || metric.footerPaddingBottom < metric.mobileRect.height + 8
  ) {
    out.push(`footer clearance=${metric.footerPaddingBottom}`);
  }
  return out;
}

function desktopViolations(metric, theme) {
  const out = [];
  if (metric.mobileDisplay !== 'none') out.push(`desktop mobile display=${metric.mobileDisplay}`);
  const visible = metric.desktop.filter(nav => nav.display !== 'none' && nav.rect && nav.rect.width > 0 && nav.rect.height > 0);
  if (visible.length !== 1) out.push(`desktop visible nav count=${visible.length}`);
  if (visible.length === 1) {
    if (visible[0].className !== THEME_NAV[theme]) {
      out.push(`desktop nav mode ${visible[0].className} != ${THEME_NAV[theme]}`);
    }
    if (!same(visible[0].labels, DESKTOP_LABELS)) {
      out.push(`desktop labels=${JSON.stringify(visible[0].labels)}`);
    }
    if (!same(visible[0].hrefs, DESKTOP_HREFS)) {
      out.push(`desktop hrefs=${JSON.stringify(visible[0].hrefs)}`);
    }
    if (!same(visible[0].activeLabels, ['今天'])) {
      out.push(`desktop active=${JSON.stringify(visible[0].activeLabels)}`);
    }
  }
  if (
    metric.scroll.htmlWidth !== metric.scroll.htmlClientWidth
    || metric.scroll.bodyWidth !== metric.scroll.bodyClientWidth
  ) {
    out.push(`desktop horizontal overflow=${JSON.stringify(metric.scroll)}`);
  }
  return out;
}

const chromePath = locateChrome();
if (!chromePath) failures.push('system Chrome/Chromium 不可用');
let chrome = null;
let cdp = null;
const browserConsoleErrors = [];
const screenshots = [];
const mobileObservations = [];
const desktopObservations = [];
const boundaryObservations = [];
const activeRouteObservations = [];
const negativeControls = [];
const evidenceDir = externalEvidenceDir ? path.resolve(externalEvidenceDir) : path.join(workRoot, 'browser-evidence');
fs.mkdirSync(evidenceDir, { recursive: true });

async function launchBrowser() {
  const profile = path.join(workRoot, 'chrome-profile');
  fs.mkdirSync(profile, { recursive: true });
  const port = await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(error => error ? reject(error) : resolve(address.port));
    });
  });
  let stderr = '';
  chrome = spawn(chromePath, [
    '--headless=new',
    '--remote-debugging-address=127.0.0.1',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-sync',
    '--disable-features=Translate,OptimizationHints,MediaRouter',
    '--metrics-recording-only',
    '--mute-audio',
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  chrome.stderr.on('data', chunk => {
    stderr += String(chunk);
  });
  let versionEndpoint = null;
  for (let attempt = 0; attempt < 200 && !versionEndpoint; attempt++) {
    if (chrome.exitCode != null) throw new Error(`Chrome 提前退出 ${chrome.exitCode}: ${stderr.slice(-2000)}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) versionEndpoint = await response.json();
    } catch {}
    if (versionEndpoint) break;
    await delay(50);
  }
  if (!versionEndpoint) throw new Error(`Chrome DevTools endpoint 超时: ${stderr.slice(-2000)}`);
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about%3Ablank`, { method: 'PUT' }).then(response => response.json());
  cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  return cdp.send('Browser.getVersion');
}

async function setPage(html, width, height, mobile) {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
  const tree = await cdp.send('Page.getFrameTree');
  await cdp.send('Page.setDocumentContent', { frameId: tree.frameTree.frame.id, html });
  await cdp.send('Runtime.evaluate', {
    expression: 'new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))',
    awaitPromise: true,
  });
}

async function evaluate(expression) {
  const response = await cdp.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result.value;
}

async function applyTheme(theme) {
  await evaluate(`(async()=>{applyTheme(${JSON.stringify(theme)});await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));return true})()`);
}

async function capture(name) {
  const result = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const bytes = Buffer.from(result.data, 'base64');
  const file = path.join(evidenceDir, `${name}.png`);
  fs.writeFileSync(file, bytes);
  const record = {
    name,
    file: externalEvidenceDir ? path.relative(evidenceDir, file) : null,
    sha256: sha256(bytes),
    bytes: bytes.length,
  };
  screenshots.push(record);
  return record;
}

function mutateMobileNav(html, transform) {
  return html.replace(
    /<nav class="nav-mobile" aria-label="移动端主导航">[\s\S]*?<\/nav>/,
    match => transform(match),
  );
}

async function runNegative(name, {
  html = routeHtml.get('/'),
  width = 375,
  height = 812,
  mobile = true,
  theme = 'warm',
  kind = 'mobile',
  expectedActive = '今天',
  after = null,
} = {}) {
  await setPage(html, width, height, mobile);
  await applyTheme(theme);
  if (after) await evaluate(after);
  const metric = await evaluate(metricExpression);
  const violations = kind === 'mobile'
    ? mobileViolations(metric, expectedActive)
    : desktopViolations(metric, theme);
  const detected = violations.length > 0;
  negativeControls.push({ name, detected, violations });
  if (!detected) failures.push(`负控未阻断: ${name}`);
}

let browserVersion = null;
try {
  if (chromePath) {
    browserVersion = await launchBrowser();
    const baseHtml = routeHtml.get('/');
    for (const theme of THEMES) {
      await setPage(baseHtml, 375, 812, true);
      await applyTheme(theme);
      const metric = await evaluate(metricExpression);
      const violations = mobileViolations(metric);
      const screenshot = await capture(`mobile-375x812-${theme}`);
      mobileObservations.push({ theme, metric, violations, screenshot });
      if (violations.length) failures.push(`mobile ${theme}: ${violations.join('; ')}`);
    }
    for (const theme of THEMES) {
      await setPage(baseHtml, 1440, 900, false);
      await applyTheme(theme);
      const metric = await evaluate(metricExpression);
      const violations = desktopViolations(metric, theme);
      const screenshot = await capture(`desktop-1440x900-${theme}`);
      desktopObservations.push({ theme, metric, violations, screenshot });
      if (violations.length) failures.push(`desktop ${theme}: ${violations.join('; ')}`);
    }
    for (const width of [779, 780]) {
      for (const theme of THEMES) {
        await setPage(baseHtml, width, 812, width < 780);
        await applyTheme(theme);
        const metric = await evaluate(metricExpression);
        const violations = width < 780 ? mobileViolations(metric) : desktopViolations(metric, theme);
        boundaryObservations.push({ width, theme, metric, violations });
        if (violations.length) failures.push(`boundary ${width}/${theme}: ${violations.join('; ')}`);
      }
    }
    for (const [route, expectedActive] of ACTIVE_ROUTES) {
      await setPage(routeHtml.get(route), 375, 812, true);
      await applyTheme('warm');
      const metric = await evaluate(metricExpression);
      const violations = mobileViolations(metric, expectedActive);
      activeRouteObservations.push({ route, expectedActive, metric, violations });
      if (violations.length) failures.push(`active route ${route}: ${violations.join('; ')}`);
    }

    await runNegative('删除 mobile nav', {
      html: mutateMobileNav(baseHtml, () => ''),
    });
    await runNegative('加入第五标签', {
      html: mutateMobileNav(baseHtml, nav => nav.replace('</nav>', '<a href="/watchlist">关注</a></nav>')),
    });
    await runNegative('移动标签错序或改名', {
      html: mutateMobileNav(baseHtml, nav => nav.replace('>队列<', '>复习<')),
    });
    await runNegative('移动 href 错配', {
      html: mutateMobileNav(baseHtml, nav => nav.replace('href="/review"', 'href="/library"')),
    });
    await runNegative('mobile 暴露 desktop nav', {
      after: `(()=>{document.querySelector('nav.nav-top').style.setProperty('display','flex','important');return true})()`,
    });
    await runNegative('breakpoint 回退到 640px', {
      html: baseHtml.replace('@media(max-width:779px)', '@media(max-width:640px)'),
      width: 700,
    });
    await runNegative('点击高度低于 44px', {
      html: baseHtml.replace('min-height:48px;padding:7px 4px', 'height:32px;min-height:32px;padding:0 4px'),
    });
    await runNegative('注入横向 overflow', {
      html: baseHtml.replace('</main>', '<div style="width:1200px;height:1px"></div></main>'),
    });
    await runNegative('桌面导航被压成四项', {
      width: 1440,
      height: 900,
      mobile: false,
      kind: 'desktop',
      after: `(()=>{document.querySelectorAll('nav.nav-top,nav.nav-side,nav.nav-dock').forEach(nav=>{while(nav.children.length>4)nav.lastElementChild.remove()});return true})()`,
    });
    await runNegative('主题 desktop nav mode 被破坏', {
      width: 1440,
      height: 900,
      mobile: false,
      kind: 'desktop',
      theme: 'cosmos',
      after: `(()=>{document.documentElement.setAttribute('data-nav','sidebar');return true})()`,
    });

    browserConsoleErrors.push(...cdp.events.filter(event => (
      event.method === 'Runtime.exceptionThrown'
      || (event.method === 'Log.entryAdded' && ['error', 'warning'].includes(event.params?.entry?.level))
      || (event.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(event.params?.type))
    )));
    if (browserConsoleErrors.length) failures.push(`browser console/page errors=${browserConsoleErrors.length}`);
  }
} catch (error) {
  failures.push(`browser harness failure: ${error.stack || error}`);
} finally {
  if (cdp) {
    try {
      await cdp.send('Browser.close');
    } catch {}
    await cdp.close();
  }
  if (chrome && chrome.exitCode == null) {
    await Promise.race([
      new Promise(resolve => chrome.once('exit', resolve)),
      delay(2000),
    ]);
  }
  if (chrome && chrome.exitCode == null) {
    chrome.kill('SIGTERM');
    await Promise.race([
      new Promise(resolve => chrome.once('exit', resolve)),
      delay(2000),
    ]);
  }
}

const report = {
  schema_version: 'adp-v12-s4-mobile-four-tab-evidence-v1',
  test_ids: {
    'TST-V12-MOBILE-NAV-SIX-THEMES': failures.length ? 'FAIL' : 'PASS',
    'TST-V12-DESKTOP-NAV-REGRESSION': failures.length ? 'FAIL' : 'PASS',
  },
  subject: {
    canonical_worker: path.relative(ROOT, LIVE_WORKER),
    canonical_worker_unchanged: fileSha256(LIVE_WORKER) === EXPECTED.liveFileSha256,
    patch_order: [
      path.relative(ROOT, PATCH_01),
      path.relative(ROOT, PATCH_02),
    ],
    patch_sha256: {
      patch01: fileSha256(PATCH_01),
      patch02: fileSha256(PATCH_02),
    },
    patch01_blob: patch01Blob,
    candidate_blob: candidateBlob,
    candidate_build_id: stamp?.[1] || null,
    candidate_source_sha256: stamp?.[2] || null,
    candidate_file_sha256: candidateFileSha256,
  },
  browser: {
    executable: chromePath,
    version: browserVersion,
    viewport_mobile: '375x812',
    viewport_desktop: '1440x900',
    screenshot_count: screenshots.length,
    console_or_page_errors: browserConsoleErrors.length,
  },
  routes: ACTIVE_ROUTES.map(([route]) => ({
    route,
    executed_worker_default_fetch: true,
    html_sha256: sha256(routeHtml.get(route) || ''),
  })),
  mobile_observations: mobileObservations,
  desktop_observations: desktopObservations,
  boundary_observations: boundaryObservations,
  active_route_observations: activeRouteObservations,
  screenshots,
  negative_controls: negativeControls,
  failures,
  verdict: failures.length ? 'FAIL' : 'PASS',
};
const reportPath = path.join(evidenceDir, 'mobile-four-tab-report.json');
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n', 'utf8');

for (const control of negativeControls) {
  console.log(`${control.detected ? 'PASS' : 'FAIL'} 负控: ${control.name}`);
}
console.log(JSON.stringify({
  verdict: report.verdict,
  test_ids: report.test_ids,
  candidate_build_id: report.subject.candidate_build_id,
  candidate_blob: report.subject.candidate_blob,
  mobile_theme_count: mobileObservations.length,
  desktop_theme_count: desktopObservations.length,
  boundary_case_count: boundaryObservations.length,
  active_route_count: activeRouteObservations.length,
  screenshot_count: screenshots.length,
  negative_controls: negativeControls.length,
  browser_errors: browserConsoleErrors.length,
  report: externalEvidenceDir ? reportPath : 'temporary',
  failures,
}, null, 2));

try {
  fs.rmSync(workRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
} catch (error) {
  console.error(`WARN 临时浏览器目录稍后需清理: ${workRoot}: ${error.message}`);
}
process.exit(failures.length ? 1 : 0);
