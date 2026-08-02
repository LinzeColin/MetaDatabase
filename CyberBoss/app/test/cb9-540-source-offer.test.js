"use strict";

// CB9-540 AGPL 对应源码入口（AC-029 / FR-029）
//
// AC-029 的 oracle：「线上 release_id、manifest digest 与对应源码页 digest 一致；
// 链接对**未登录网络用户**可见。」
//
// 这个节点在任务包里是 environment_bound——「线上一致」那半必须在真实部署上验。
// 但它有一半根本不依赖环境，而且那一半在此之前是**完全缺失**的：
//
//   这个产品是 AGPL-3.0（仓库根目录那份 LICENSE），而任何一个服务出去的页面上
//   都没有对应源码入口。不是入口做得不好，是根本没有。AGPL 第 13 条要求通过网络
//   提供服务时必须给使用者取得对应源码的途径——这是许可证义务，不是产品特性。
//
// 所以这一套测试覆盖能在本地做完、且做完就是真的那一半：入口在不在、免不免鉴权、
// 摘要算得对不对、算法稳不稳定。**线上那半是 NOT_RUN，本地这份不许拿去顶。**

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const test = require("node:test");

const { PortalHttpServer } = require("../src/services/portal/portal-server");
const {
  LICENSE_ID,
  SOURCE_ROOTS,
  SOURCE_URL,
  buildSourceOffer,
  listSourceFiles,
  renderSourcePage,
  sourceManifest,
} = require("../src/services/release/source-offer");

const PROJECT_ROOT = path.join(__dirname, "..", "..");

function get(port, requestPath, headers = {}) {
  return new Promise((resolve, reject) => {
    const call = http.request(
      { host: "127.0.0.1", port, method: "GET", path: requestPath, headers },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => resolve({
          status: response.statusCode,
          headers: response.headers,
          text: Buffer.concat(chunks).toString("utf8"),
        }));
      },
    );
    call.on("error", reject);
    call.end();
  });
}

async function server(t, extra = {}) {
  const instance = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "panel-token",
    firstRunProvider: () => false,
    logger: { warn() {} },
    ...extra,
  });
  const address = await instance.start();
  t.after(() => instance.stop());
  return address.port;
}

// ── AC-029 入口对未登录用户可见 ──────────────────────────

test("AC-029 /source 不要任何凭据就能打开", async (t) => {
  // 「免鉴权」是硬要求，不是方便。使用者是那些扫码进来聊天的人，把源码链接放在
  // 后台里等于没放——他们永远看不到后台。
  const port = await server(t);
  const page = await get(port, "/source");
  assert.equal(page.status, 200);
  assert.match(page.headers["content-type"], /text\/html/);
  assert.ok(page.text.includes(SOURCE_URL), "页面上没有源码地址");
  assert.ok(page.text.includes("AGPL"), "页面上没说许可证");
});

test("AC-029 带一个错令牌也照样打得开", async (t) => {
  // 反面：如果它其实是被鉴权守着的，错令牌会 401。
  const port = await server(t);
  const page = await get(port, "/source", { "x-admin-token": "wrong" });
  assert.equal(page.status, 200);
});

test("AC-029 三个服务出去的页面上都有这个入口", () => {
  // 一个谁都找不到的 /source 不叫入口。AGPL 第 13 条要的是使用者**能拿到**，
  // 而使用者只会看到这三页。
  for (const template of ["home.html", "join.html", "me.html"]) {
    const html = fs.readFileSync(
      path.join(__dirname, "..", "templates", template), "utf8");
    assert.ok(html.includes('href="/source"'), `${template} 上没有对应源码入口`);
  }
});

test("AC-029 /source 和 /source/ 都认", async (t) => {
  // 末尾斜杠差一个字符就 404，是这类静态入口最常见的死法。
  const port = await server(t);
  for (const p of ["/source", "/source/"]) {
    assert.equal((await get(port, p)).status, 200, `${p} 打不开`);
  }
});

// ── AC-029 摘要 ──────────────────────────────────────────

test("AC-029 摘要只覆盖真正发出去的源码", () => {
  // 覆盖整个仓的话，改一份证据文档就会让摘要变——而摘要变了意味着「线上跑的
  // 东西换了」，那是在制造假警报。假警报多了，真的那次也没人看。
  assert.deepEqual([...SOURCE_ROOTS], ["app/src", "app/templates", "app/migrations"]);
  const files = listSourceFiles(PROJECT_ROOT);
  assert.ok(files.length > 100, `只找到 ${files.length} 个源文件——路径大概是错的`);
  for (const file of files) {
    assert.ok(!file.includes("node_modules"), "把依赖也算进去了");
    assert.ok(!file.includes("/docs/"), "把文档也算进去了");
    assert.ok(!file.includes("/test/"), "把测试也算进去了");
  }
});

test("AC-029 同一份源码算两次得同一个摘要", () => {
  // 不稳定的话，「摘要对不上」会被读成「线上跑的不是这份源码」——
  // 而使用者拿它去对公开源码，对不上就会以为我们藏了改动。
  assert.equal(
    sourceManifest({ projectRoot: PROJECT_ROOT }).digest,
    sourceManifest({ projectRoot: PROJECT_ROOT }).digest,
  );
});

test("AC-029 摘要不跟目录遍历顺序走", () => {
  const manifest = sourceManifest({ projectRoot: PROJECT_ROOT });
  const paths = manifest.entries.map((entry) => entry.path);
  assert.deepEqual(paths, [...paths].sort(),
    "条目没排序——同一份源码在两台机器上会算出两个值");
});

test("AC-029 改一个字节，摘要就变", () => {
  // 摘要不敏感的话，「线上跑的是这份源码」这句话就没有证据。
  const tempRoot = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "cb-src-"));
  try {
    const dir = path.join(tempRoot, "app", "src");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "a.js"), "module.exports = 1;\n");
    const before = sourceManifest({ projectRoot: tempRoot }).digest;
    fs.writeFileSync(path.join(dir, "a.js"), "module.exports = 2;\n");
    assert.notEqual(sourceManifest({ projectRoot: tempRoot }).digest, before);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AC-029 把一段从一个文件挪到另一个，摘要也要变", () => {
  // 直接把所有内容拼起来算的话，这种挪动摘要不变——而它们是两份不同的源码。
  // 所以摘要算的是「路径 + 每个文件的摘要」这张表，不是内容的拼接。
  const tempRoot = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "cb-src-"));
  try {
    const dir = path.join(tempRoot, "app", "src");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "a.js"), "const x = 1;\nconst y = 2;\n");
    fs.writeFileSync(path.join(dir, "b.js"), "const z = 3;\n");
    const before = sourceManifest({ projectRoot: tempRoot }).digest;
    fs.writeFileSync(path.join(dir, "a.js"), "const x = 1;\n");
    fs.writeFileSync(path.join(dir, "b.js"), "const y = 2;\nconst z = 3;\n");
    assert.notEqual(sourceManifest({ projectRoot: tempRoot }).digest, before);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AC-029 只改文件名、内容一个字节不动，摘要也要变", () => {
  // 变异测试抓到的：把摘要里的路径去掉、只对内容摘要求和，上面那条「挪一段」
  // 依然红不了——挪动会同时改掉两个文件的 sha256。路径真正挡住的是**改名**：
  // 两份只有文件名不同的源码，不带路径的话算出同一个摘要。
  //
  // 而改名是一份不同的源码：使用者按公开源码里的路径去找，找不到。
  const os = require("node:os");
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cb-src-"));
  try {
    const dir = path.join(tempRoot, "app", "src");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "a.js"), "const x = 1;\n");
    const before = sourceManifest({ projectRoot: tempRoot }).digest;
    fs.renameSync(path.join(dir, "a.js"), path.join(dir, "b.js"));
    assert.notEqual(sourceManifest({ projectRoot: tempRoot }).digest, before,
      "改了文件名摘要没变——摘要里没带路径");
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AC-029 依赖目录不算进摘要", () => {
  // 当前这三个源码根下面本来就没有 node_modules，所以那句跳过在真实树上
  // **不承重**——删掉它测试照样全绿（变异测试那一刀是活的）。
  //
  // 但它不是白写的：哪天源码根扩到一个含依赖的目录，摘要会跟着依赖的安装
  // 结果变，而那意味着同一份源码在两台机器上算出两个值。用一棵临时树把这条
  // 钉住，那句跳过就承重了。
  const os = require("node:os");
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cb-src-"));
  try {
    const dir = path.join(tempRoot, "app", "src");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "a.js"), "const x = 1;\n");
    const before = sourceManifest({ projectRoot: tempRoot }).digest;

    const vendor = path.join(dir, "node_modules", "left-pad");
    fs.mkdirSync(vendor, { recursive: true });
    fs.writeFileSync(path.join(vendor, "index.js"), "module.exports = () => {};\n");
    assert.equal(sourceManifest({ projectRoot: tempRoot }).digest, before,
      "装一个依赖就把源码摘要改了");
    assert.deepEqual(
      listSourceFiles(tempRoot).map((f) => path.basename(f)), ["a.js"],
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

// ── AC-029 没上线时说实话 ────────────────────────────────

test("AC-029 没有 release_id 时显示 unreleased，不编一个", () => {
  // 编一个的话，使用者拿着它去对公开源码，对不上，然后他会以为我们藏了改动。
  const offer = buildSourceOffer({ projectRoot: PROJECT_ROOT });
  assert.equal(offer.release_id, "unreleased");
  assert.equal(offer.license, LICENSE_ID);
  assert.match(offer.manifest_digest, /^[0-9a-f]{64}$/);
});

test("AC-029 给了 release_id 就用真的那个", async (t) => {
  const port = await server(t, { releaseIdProvider: () => "release-v0.0.0.9-abc1234" });
  const page = await get(port, "/source");
  assert.ok(page.text.includes("release-v0.0.0.9-abc1234"), "线上版本没印出来");
});

test("AC-029 源码地址是任何人都打得开的那个形式", () => {
  // 从 git remote 读的话会读到 git@github.com:... —— 那个印在公开页上，
  // 对使用者等于没有。
  assert.match(SOURCE_URL, /^https:\/\//);
  assert.ok(!SOURCE_URL.startsWith("git@"));
});

// ── 页面本身 ─────────────────────────────────────────────

test("AC-029 页面把值转义，不直接拼进 HTML", () => {
  const html = renderSourcePage({
    license: LICENSE_ID,
    source_url: SOURCE_URL,
    release_id: '"><script>alert(1)</script>',
    manifest_digest: "a".repeat(64),
    file_count: 1,
    generated_at: "2026-08-02T12:00:00.000Z",
  });
  assert.ok(!html.includes("<script>alert(1)</script>"), "release_id 被原样拼进去了");
  assert.ok(html.includes("&lt;script&gt;"));
});

test("AC-029 算不出摘要时不回 404", async (t) => {
  // 404 读起来像「这个服务不提供源码」——那是一句关于许可证的错话。
  const port = await server(t, {
    releaseIdProvider: () => { throw new Error("boom"); },
  });
  const page = await get(port, "/source");
  assert.notEqual(page.status, 404);
  assert.ok(page.text.includes(SOURCE_URL), "连源码地址都没给");
});

// ── 第十次的那条：注入了但没接住 ─────────────────────────

test("每一个 app.js 注入给 portal 的字段都真的被接住了", () => {
  // releaseIdProvider 是这个仓**第十次**栽在同一件事上：app.js 注入了、
  // 路由也挂了、页面也出得来，只是构造函数的解构清单里没有它，于是
  // this.releaseIdProvider 是 undefined，那一格永远显示 unreleased。
  //
  // 构造函数里那段注释数到第九次就停了——读到教训防不住按名字解构。能防住的
  // 只有守卫。所以把它从「记得加」变成结构检查：
  //
  //   把 app.js 里那份注入清单的每个键都塞一个**独一无二的哨兵**，构造出来
  //   之后在实例上找它。找不到就是被静默丢掉了。
  //
  // 这条会连带发现另一种漏法：解构了但忘了 this.x = x。
  const appSource = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = appSource.indexOf("new PortalHttpServer({");
  assert.ok(start > 0, "app.js 里找不到 PortalHttpServer 的构造点");

  // 只取这一个对象字面量：从 `({` 到缩进对齐的 `});`。
  const body = appSource.slice(start, appSource.indexOf("\n    });", start));
  // 顶层键：正好四个空格缩进的 `名字:`。更深的缩进是嵌套对象里的。
  const injected = [...body.matchAll(/^ {6}([a-zA-Z_][a-zA-Z0-9_]*):/gm)].map((m) => m[1]);
  assert.ok(injected.length > 20, `只解析出 ${injected.length} 个注入字段——正则大概不对`);

  const sentinels = new Map(injected.map((key) => [key, `__sentinel_${key}__`]));
  const instance = new PortalHttpServer({
    ...Object.fromEntries(sentinels),
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    logger: { warn() {} },
  });
  const landed = new Set(Object.values(instance));
  const dropped = injected.filter((key) => {
    const sentinel = sentinels.get(key);
    // portal / port / logger 被上面覆盖掉了，不算。
    return !["portal", "port", "logger"].includes(key) && !landed.has(sentinel);
  });
  assert.deepEqual(dropped, [],
    `这几个字段注入了但没被接住，线上会静默失效：${dropped.join(", ")}`);
});

// ── 空集合不许当成一份摘要 ───────────────────────────────

test("AC-029 一个源文件都没扫到时，不发摘要而是报错", (t) => {
  // 空集合算出来的是 e3b0c44298fc1c14…b855——空字符串的 sha256。它长得和一个
  // 正常摘要一模一样，页面照样渲染、照样权威，而它在法律上什么都没证明。
  //
  // 这不是假想：projectRoot 传成 app/ 而不是仓库根就正好落进这一格
  // （SOURCE_ROOTS 是 "app/src" 这样的相对路径）。2026-08-02 核对 AC-029 时
  // 第一次就踩中了，而症状只是文件数从 272 悄悄变成 0。
  const empty = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "cb-src-empty-"));
  t.after(() => fs.rmSync(empty, { recursive: true, force: true }));
  assert.throws(
    () => buildSourceOffer({ projectRoot: empty }),
    (error) => error.code === "SOURCE_MANIFEST_EMPTY",
    "空集合被当成了一份合法摘要",
  );
});

test("AC-029 空字符串的 sha256 绝不能出现在任何一份 offer 里", () => {
  // 结构性的：上一条靠「目录是空的」触发。这一条直接盯住那个常量本身——
  // 无论以后怎么改，只要有人算出了它，就说明摘要盖的是一个空集合。
  const EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  const offer = buildSourceOffer({
    projectRoot: path.resolve(__dirname, "..", ".."),
    releaseId: "test-release",
  });
  assert.notEqual(offer.manifest_digest, EMPTY_SHA256, "摘要盖的是一个空集合");
  assert.ok(offer.file_count > 0, "文件数是 0，摘要没有覆盖任何东西");
});

// ── HEAD 不能把好页面报成 404 ─────────────────────────────

test("AC-035 探活用的 HEAD 不能把活着的页面报成 404", async (t) => {
  // 2026-08-02 在真站上量出来：**每一个**公开路径 HEAD 都回 404，包括 /healthz。
  // 而探活监控普遍默认用 HEAD——它会一直报「站挂了」，而站是好的。
  //
  // 这正是这套系统最不该犯的那种错：面板指着一个不存在的故障。指多了，
  // 真出事那天就没人当回事了。
  // 用这个文件里现成的那个真服务 helper，不自己再拼一个——参数拼错了会
  // 让这条测试因为构造失败而红，看起来像 HEAD 有问题，实际不是。
  const port = await server(t, { releaseIdProvider: () => "headtest" });
  const base = `http://127.0.0.1:${port}`;

  const call = (method, pathname) => new Promise((resolve, reject) => {
    const req = http.request(`${base}${pathname}`, { method }, (res) => {
      res.resume();
      res.on("end", () => resolve({ status: res.statusCode, type: res.headers["content-type"] || "" }));
    });
    req.on("error", reject);
    req.end();
  });

  for (const pathname of ["/", "/join", "/source", "/healthz"]) {
    const get = await call("GET", pathname);
    const head = await call("HEAD", pathname);
    assert.equal(head.status, get.status,
      `HEAD ${pathname} 回 ${head.status}，GET 回 ${get.status}——探活监控会误报`);
    assert.equal(head.type.split(";")[0], get.type.split(";")[0],
      `HEAD ${pathname} 的 content-type 和 GET 不一样`);
  }
});

test("AC-035 会产生副作用的接口不许被 HEAD 触发", async (t) => {
  // /api/join 的 GET 会**发一张新票**。让 HEAD 也能发，等于多了一条不留正文
  // 痕迹的方式去消耗票池。监控探的是页面，不是发票接口。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "portal", "portal-server.js"), "utf8");
  const start = source.indexOf("const HEAD_READABLE_PATHS");
  assert.ok(start > 0, "找不到 HEAD 白名单");
  const list = source.slice(start, source.indexOf("]);", start));
  assert.ok(!list.includes("/api/"), "把接口放进 HEAD 白名单了");
  assert.ok(list.includes("/healthz"), "探活路径不在 HEAD 白名单里");
});
