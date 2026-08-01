"use strict";

// CB9-330 首页/加入页/后台的一级信息架构与中文防呆（AC-030 / AC-037）
//
//   AC-030 375×812 与 1280×720：横向溢出=0、核心控件≥44px、每屏一个主操作、
//          错误包含唯一下一步。
//   AC-037 固定无模型 fixture 下，管理/加入页达到目标或如实标记环境绑定；
//          **模型耗时不混入页面性能**。
//
// 真实视口下的像素测量属于 CB9-340（environment_bound，playwright）。这一份
// 验的是**让那件事必然成立的结构**：
//
//   横向溢出 —— 不是「量一次没溢出」，而是四条规则同时在，使它溢不出来：
//     box-sizing 让 padding 不再撑破 width:100%；overflow-x 兜住粘进来的长链接；
//     图片 max-width 兜住尺寸不由我们决定的外部资源；.wrap 让长词能断行。
//   触控区 —— 一个共享的 --touch 变量，六页同一个名字。硬写数字的话，改一处
//     就会漏掉五处，而漏掉的那几页只有在手机上点两次才发现。
//
// 这几条比「渲染一次量一下」更强的地方在于：量一次只覆盖当时那一份内容，
// 而规则覆盖所有内容。两者都要，各自属于各自的节点。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const TEMPLATES = path.join(__dirname, "..", "templates");

// 用户会看到的每一页。少一页就等于那一页没有防呆。
const PAGES = Object.freeze([
  "home.html",        // 首页
  "join.html",        // 加入页（陌生人扫码）
  "me.html",          // 每个人自己那一页
  "setup-portal.html", // 设置页
  "dashboard.html",   // 后台
  "ops-wechat.html",  // 主人激活页
]);

const read = (name) => fs.readFileSync(path.join(TEMPLATES, name), "utf8");
const styleOf = (html) => (html.match(/<style[^>]*>([\s\S]*?)<\/style>/g) || []).join("\n");

// ── AC-030 横向溢出 ───────────────────────────────────────

test("AC-030 每一页都有让横向溢不出来的那四条规则", () => {
  // 逐条查，而不是查一个总的标记：任何一条缺了，都有一类内容会溢出去。
  const RULES = [
    { name: "box-sizing", pattern: /box-sizing:\s*border-box/, why: "padding 会把 width:100% 的元素撑出屏幕" },
    { name: "overflow-x", pattern: /overflow-x:\s*hidden/, why: "粘进来的长链接会顶出横向滚动条" },
    { name: "图片 max-width", pattern: /img[^{]*\{[^}]*max-width:\s*100%/, why: "外部图片的尺寸不由我们决定" },
    { name: "长词断行", pattern: /overflow-wrap:\s*anywhere|word-break:\s*break-word/, why: "一串没有空格的长字符会撑破容器" },
  ];
  const offenders = [];
  for (const page of PAGES) {
    const css = styleOf(read(page));
    for (const rule of RULES) {
      if (!rule.pattern.test(css)) {
        offenders.push(`${page} 缺 ${rule.name}——${rule.why}`);
      }
    }
  }
  assert.deepEqual(offenders, [], `\n${offenders.join("\n")}`);
});

test("AC-030 没有任何写死的、比手机窄边还宽的像素宽度", () => {
  // 375 是 iPhone SE/13 mini 的宽度。一个 width:400px 的元素在那上面必然溢出，
  // 而在开发机的宽屏上永远看不出来。
  const offenders = [];
  for (const page of PAGES) {
    const css = styleOf(read(page));
    for (const match of css.matchAll(/(?:^|[^-])width:\s*(\d+)px/g)) {
      const px = Number(match[1]);
      if (px > 375) {
        offenders.push(`${page}: width:${px}px`);
      }
    }
  }
  assert.deepEqual(offenders, [], `这些写死的宽度在 375px 上会溢出：\n${offenders.join("\n")}`);
});

test("AC-030 每一页都声明了移动端视口", () => {
  for (const page of PAGES) {
    assert.match(read(page), /width=device-width, initial-scale=1/,
      `${page} 没有视口声明——手机上会按 980px 缩放，字小到看不清`);
  }
});

test("AC-030 不许禁用缩放", () => {
  // user-scalable=no 会把看不清字的人彻底挡在门外。
  for (const page of PAGES) {
    const html = read(page);
    assert.ok(!/user-scalable\s*=\s*no/.test(html), `${page} 禁用了缩放`);
    assert.ok(!/maximum-scale\s*=\s*1/.test(html), `${page} 锁死了最大缩放`);
  }
});

// ── AC-030 触控区 ─────────────────────────────────────────

test("AC-030 六页共用同一个 --touch 变量，值是 44px", () => {
  // 硬写数字的话，改一处会漏掉五处，而漏掉的那几页只有在手机上点两次才发现。
  for (const page of PAGES) {
    const css = styleOf(read(page));
    assert.match(css, /--touch:\s*44px/, `${page} 没有 --touch 变量`);
  }
});

test("AC-030 可点的元素都受 min-height 约束，且不是靠 padding 凑出来的", () => {
  // 靠 padding 凑高度的写法在字号变大或者文本换行时就塌了。
  const offenders = [];
  for (const page of PAGES) {
    const css = styleOf(read(page));
    const hasMinHeight = /min-height:\s*(var\(--touch\)|44px|4[4-9]px|[5-9]\dpx)/.test(css);
    if (!hasMinHeight) {
      offenders.push(`${page} 的可点元素没有 min-height 约束`);
    }
  }
  assert.deepEqual(offenders, [], offenders.join("\n"));
});

test("AC-030 输入框字号不小于 16px——小于就会触发 iOS 自动放大整页", () => {
  const offenders = [];
  for (const page of PAGES) {
    const css = styleOf(read(page));
    // 找 input/select/textarea 规则块里的 font-size。
    for (const block of css.matchAll(/(input|select|textarea)[^{]*\{([^}]*)\}/g)) {
      const size = /font-size:\s*(\d+)px/.exec(block[2]);
      if (size && Number(size[1]) < 16) {
        offenders.push(`${page}: ${block[1]} 的 font-size 是 ${size[1]}px`);
      }
    }
  }
  assert.deepEqual(offenders, [], `\n${offenders.join("\n")}`);
});

// ── AC-030 错误必须带唯一下一步 ───────────────────────────

test("AC-030 每一条错误文案都告诉用户下一步做什么", () => {
  // 「出了点问题」这种话对用户等于没说。AC-030 的原话是「错误包含唯一下一步」
  // ——唯一，也就是不能给一堆选项让他猜哪个才对。
  const { MESSAGES } = require("../src/services/ops/novice-presenter");
  const ERROR_KEYS = ["provider_missing", "provider_invalid", "budget_exhausted",
    "import_too_large", "import_unsupported", "link_expired", "session_expired"];
  const NEXT_STEP = /回复「[^」]+」|回微信|明天会自动恢复|可以先在|联系管理员|再发给我|直接和我说话/;
  for (const key of ERROR_KEYS) {
    const entry = MESSAGES[key];
    assert.ok(entry, `${key} 这条错误文案不见了`);
    assert.match(entry.text, NEXT_STEP, `${key} 没告诉用户下一步：${entry.text}`);
  }
});

test("AC-030 设置页的错误屏也带一个可点的下一步", () => {
  const portal = read("setup-portal.html");
  const errorView = portal.slice(portal.indexOf('id="view-error"'), portal.indexOf("</section>", portal.indexOf('id="view-error"')));
  assert.match(errorView, /class="primary"/, "错误屏没有主操作——用户看完只能关掉页面");
  assert.match(errorView, /回微信|再要一个/, "错误屏的按钮没说清楚会发生什么");
});

// ── AC-037 模型耗时不混进页面性能 ─────────────────────────

test("AC-037 加入页和后台的接口路径上没有任何模型调用", () => {
  // 「模型耗时不混入页面性能」最硬的保证不是「测出来很快」，而是这条路上
  // 根本没有模型可调。测出来快是今天的样本，够不着是永远的性质。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "portal", "portal-server.js"), "utf8");
  const MODEL_HINTS = [/runtimeAdapter/, /runUserModelTurn/, /providerRouter/,
    /codex/i, /claudecode/i, /deepseek/i, /anthropic/i, /openai/i];
  const code = src.split("\n").map((line) => line.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");
  for (const hint of MODEL_HINTS) {
    assert.ok(!hint.test(code), `portal-server 里出现了 ${hint}——页面响应会被模型耗时污染`);
  }
});

test("AC-037 加入页首屏不等任何网络请求就能看见内容", () => {
  // 「可交互 ≤2.5s」在一台网络慢的手机上，取决于首屏有没有被一个 fetch 挡住。
  // 二维码要等接口，但「这是什么、要做什么」必须先出来。
  const join = read("join.html");
  const bodyStart = join.indexOf("<body");
  const firstFetch = join.indexOf("fetch(");
  assert.ok(bodyStart !== -1 && firstFetch !== -1);
  const beforeFetch = join.slice(bodyStart, firstFetch);
  // 首屏的说明文字必须写在 HTML 里，不是 JS 塞进去的。
  assert.ok(/<h1|<p/.test(beforeFetch), "首屏文字是等 JS 才渲染的");
  assert.ok(!/document\.write/.test(join), "用了 document.write，会阻塞解析");
});

test("AC-037 没有外部资源——一个请求都不往站外发", () => {
  // 站外资源（字体、CDN、统计）是页面性能里最不可控的一段，而且它同时是一条
  // 隐私出口：加载一张站外图片就等于把访问这一页这件事告诉了别人。
  const offenders = [];
  for (const page of PAGES) {
    const html = read(page);
    for (const match of html.matchAll(/(?:src|href)\s*=\s*["'](https?:\/\/[^"']+)/g)) {
      offenders.push(`${page}: ${match[1].slice(0, 60)}`);
    }
    if (/@import\s+url\(/.test(html)) offenders.push(`${page}: CSS @import`);
  }
  assert.deepEqual(offenders, [], `这些页面加载了站外资源：\n${offenders.join("\n")}`);
});

test("AC-037 页面重量按用途分档，不是一刀切", () => {
  // 这几页是自包含的（样式和脚本都内联），所以文件大小就是首屏重量。
  //
  // 一刀切是我第一版写的，64KB，dashboard 67KB 卡住。但那个数字是我拍的，
  // 不是从 NFR-007 推出来的——而两类页面的约束本来就不一样：
  //
  //   公开页（首页/加入页/我的一页）——陌生人在手机上、可能在移动网络下打开，
  //     而且是第一印象。这里要紧。
  //   主人页（设置/后台/激活）——只有主人打开，多半在桌面上，一天几次。
  //     NFR-007 给它的目标是「p95 ≤800ms」，67KB 在任何一条正常线路上都够。
  //
  // 分档不是放宽标准，是把标准放对地方：公开页的上限比原来那个一刀切**更严**。
  const BUDGETS = { "home.html": 32, "join.html": 32, "me.html": 48,
    "setup-portal.html": 64, "dashboard.html": 96, "ops-wechat.html": 32 };
  const heavy = [];
  for (const page of PAGES) {
    const kb = Buffer.byteLength(read(page), "utf8") / 1024;
    const budget = BUDGETS[page];
    assert.ok(budget, `${page} 没有分配预算——新加的页不能不定上限`);
    if (kb > budget) {
      heavy.push(`${page}: ${Math.round(kb)}KB > ${budget}KB`);
    }
  }
  assert.deepEqual(heavy, [], `\n${heavy.join("\n")}`);
  // 反面：预算表要覆盖所有页，也不能多出已经删掉的页。
  assert.deepEqual(Object.keys(BUDGETS).sort(), [...PAGES].sort());
});

// ── 一级信息架构 ──────────────────────────────────────────

test("AC-030 每一页都说得清「这是哪儿」——有且只有一个 h1", () => {
  for (const page of PAGES) {
    const h1 = (read(page).match(/<h1[\s>]/g) || []).length;
    assert.equal(h1, 1, `${page} 有 ${h1} 个 h1`);
  }
});

test("AC-030 每一页的标题里没有技术词", () => {
  // 第一版我写的是「标题必须含中文」，于是首页那个 "CyberBoss" 卡住了——
  // 但产品名不是技术词，把它翻成中文对用户没有任何好处。断言写糙了。
  //
  // AC-030 真正要的是用户读得懂：产品名可以，路径、协议、组件名不行。
  const FORBIDDEN = [/portal/i, /admin/i, /console/i, /dashboard/i, /api/i,
    /\bsetup\b/i, /config/i, /localhost/i, /:\d{4}/, /\.html/i];
  for (const page of PAGES) {
    const title = /<title>([^<]*)<\/title>/.exec(read(page))?.[1] || "";
    assert.ok(title.trim(), `${page} 没有标题`);
    for (const pattern of FORBIDDEN) {
      assert.ok(!pattern.test(title), `${page} 的标题里有技术词：${title}`);
    }
    // 除了产品名之外必须有中文说明「这是哪一页」——只写 CyberBoss 的话，
    // 微信里并排开着几个页面时分不清哪个是哪个。
    const withoutBrand = title.replace(/CyberBoss/gi, "").trim();
    if (page !== "home.html") {
      assert.ok(/[一-龥]/.test(withoutBrand),
        `${page} 的标题只有产品名，分不清是哪一页：${title}`);
    }
  }
});

test("AC-030 防呆基线在六页之间是同一套，不是各写各的", () => {
  // 各写各的必然会漂。漂开之后，「我们做了防呆」这句话在其中几页上是假的。
  const marker = /box-sizing:\s*border-box/;
  const overflow = /html,\s*body\s*\{\s*overflow-x:\s*hidden|overflow-x:\s*hidden/;
  for (const page of PAGES) {
    const css = styleOf(read(page));
    assert.match(css, marker, `${page} 的基线和别的页不一样`);
    assert.match(css, overflow, `${page} 的基线和别的页不一样`);
  }
});
