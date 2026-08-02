"use strict";

// AGPL 对应源码入口（CB9-540 / AC-029、FR-029）。
//
// FR-029 的原话：「线上页面提供对应源码入口，release manifest 与公开源码摘要匹配。」
// AC-029 的 oracle：「线上 release_id、manifest digest 与对应源码页 digest 一致；
// 链接对**未登录网络用户**可见。」
//
// 这不是锦上添花的一页。AGPL-3.0 第 13 条：通过网络提供服务时，必须给使用者
// 取得对应源码的途径。这个产品是 AGPL（仓库根目录那份 LICENSE），而在此之前
// **任何一个页面上都没有这个入口**——不是入口做得不好，是根本没有。
//
// 「未登录可见」这条要紧：把源码链接放在后台里等于没放，因为使用者是那些扫码
// 进来聊天的人，他们永远看不到后台。
//
// 这个模块只做能在本地做完、且做完就是真的那一半：算出 manifest 摘要、拼出
// 这一页的内容。**线上那半（release_id 对得上、页面公网可达）必须在真实环境
// 里验，验不了就是 NOT_RUN，不许拿本地这份顶。**

const fs = require("node:fs");
const path = require("node:path");
const { createHash } = require("node:crypto");

const LICENSE_ID = "AGPL-3.0-or-later";

// 公开源码的位置。
//
// 写成常量而不是从 git remote 读：remote 会随着谁 clone 的、用什么协议而变
// （git@ 和 https:// 是两个串），而这一页上印的必须是**任何人都打得开的那个**。
// 一个 ssh 形式的 URL 印在公开页上，对使用者等于没有。
const SOURCE_URL = "https://github.com/LinzeColin/MetaDatabase";

// 摘要只覆盖真正发出去的源码。
//
// 覆盖整个仓的话，改一份证据文档就会让摘要变——而摘要变了就意味着「线上跑的
// 东西换了」，那是在制造假警报。假警报多了，真的那次也没人看。
const SOURCE_ROOTS = Object.freeze(["app/src", "app/templates", "app/migrations"]);

const SOURCE_EXTENSIONS = Object.freeze([".js", ".sql", ".html", ".css"]);

class SourceOfferError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "SourceOfferError";
    this.code = code;
    this.detail = detail;
  }
}

function listSourceFiles(projectRoot) {
  const found = [];
  for (const root of SOURCE_ROOTS) {
    const base = path.join(projectRoot, root);
    if (!fs.existsSync(base)) {
      continue;
    }
    const stack = [base];
    while (stack.length > 0) {
      const current = stack.pop();
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "node_modules") {
            stack.push(full);
          }
          continue;
        }
        if (SOURCE_EXTENSIONS.includes(path.extname(entry.name))) {
          found.push(full);
        }
      }
    }
  }
  // 排序，否则摘要跟着目录遍历顺序走——同一份源码在两台机器上会算出两个值，
  // 而「摘要对不上」会被读成「线上跑的不是这份源码」。
  return found.sort();
}

// 对应源码的摘要。
//
// 逐文件算 sha256，再对「路径 + 摘要」这张排好序的表算一次 sha256。
// 直接把所有文件内容拼起来算的话，把 a.js 的末尾挪到 b.js 的开头摘要不变——
// 而那是两份不同的源码。
function sourceManifest({ projectRoot }) {
  const files = listSourceFiles(projectRoot);
  const entries = files.map((file) => ({
    path: path.relative(projectRoot, file).split(path.sep).join("/"),
    sha256: createHash("sha256").update(fs.readFileSync(file)).digest("hex"),
  }));
  // 分隔符写成**转义的** U+0000，不是裸字节、也不是空格。
  //
  // 裸字节会让 grep 和 diff 把整个源文件当成二进制——这一程里我已经栽过四次，
  // 这次又是它（本来想打个空格，落进去的是 0x00）。
  //
  // 空格则是正确性问题：路径里有空格的话，("a b", h) 和 ("a", "b" + h) 会拼出
  // 同一个串，两份不同的源码算出同一个摘要。
  // 一个文件都没扫到，就不发摘要。
  //
  // 空集合算出来的是 e3b0c44298fc1c14…b855——空字符串的 sha256。它长得和一个
  // 正常摘要一模一样，页面照样渲染、照样权威，而它在法律上什么都没证明：
  // AGPL §13 要的是「你正在跑的这份源码」的凭据，不是一个恰好自洽的常量。
  //
  // 这不是假想：projectRoot 传成 app/ 而不是仓库根，就正好落进这一格
  // （SOURCE_ROOTS 是 "app/src" 这样的相对路径）。而失败方式是**静默的**——
  // 摘要还在、页面还在，只有文件数悄悄变成 0。哪天有人挪了目录结构，
  // 这一页会继续每天对全世界公布一个空摘要。
  if (entries.length === 0) {
    throw new SourceOfferError("SOURCE_MANIFEST_EMPTY", String(projectRoot || ""));
  }
  const digest = createHash("sha256")
    .update(entries.map((entry) => `${entry.path}\u0000${entry.sha256}`).join("\n"))
    .digest("hex");
  return Object.freeze({
    file_count: entries.length,
    digest,
    entries: Object.freeze(entries),
  });
}

// 这一页要显示的东西。
//
// release_id 由调用方给（它来自真实的部署，本地算不出来）；给不出来时显示
// "unreleased"，**不显示一个编出来的**。编一个的话，使用者拿着它去对公开源码，
// 对不上，然后他会以为我们藏了改动。
function buildSourceOffer({ projectRoot, releaseId = null, generatedAt = new Date() } = {}) {
  const manifest = sourceManifest({ projectRoot });
  const stamp = new Date(generatedAt);
  return Object.freeze({
    license: LICENSE_ID,
    source_url: SOURCE_URL,
    release_id: releaseId ? String(releaseId) : "unreleased",
    manifest_digest: manifest.digest,
    file_count: manifest.file_count,
    generated_at: Number.isFinite(stamp.getTime())
      ? stamp.toISOString()
      : new Date(0).toISOString(),
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

// 整页 HTML。
//
// 不用模板文件：这一页必须在**任何**情况下都能出得来，包括模板目录读不到的时候。
// AGPL 第 13 条不接受「我们的模板加载器当时挂了」这个理由。
function renderSourcePage(offer) {
  const rows = [
    ["许可证", offer.license],
    ["对应源码", offer.source_url],
    ["线上版本", offer.release_id],
    ["源码摘要", offer.manifest_digest],
    ["文件数", String(offer.file_count)],
  ];
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>对应源码</title>
<style>
body{font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
margin:0;padding:32px 20px;color:#1a1a1a;background:#fafafa}
main{max-width:640px;margin:0 auto}
h1{font-size:22px;margin:0 0 8px}
p{margin:0 0 20px;color:#555}
dl{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0;
background:#fff;padding:20px;border-radius:12px;border:1px solid #e5e5e5}
dt{color:#666;white-space:nowrap}
dd{margin:0;word-break:break-all;font-family:ui-monospace,SFMono-Regular,monospace;font-size:14px}
a{color:#0b62d6}
@media (prefers-color-scheme:dark){
body{background:#141414;color:#eee}dl{background:#1e1e1e;border-color:#333}
dt{color:#999}a{color:#6aa9ff}}
</style>
</head>
<body>
<main>
<h1>对应源码</h1>
<p>这个服务按 GNU AGPL-3.0 授权。你有权取得它正在运行的这份源码。</p>
<dl>
${rows.map(([label, value]) => `  <dt>${escapeHtml(label)}</dt>\n  <dd>${
  label === "对应源码"
    ? `<a href="${escapeHtml(value)}" rel="noopener">${escapeHtml(value)}</a>`
    : escapeHtml(value)
}</dd>`).join("\n")}
</dl>
</main>
</body>
</html>
`;
}

module.exports = {
  SourceOfferError,
  LICENSE_ID,
  SOURCE_EXTENSIONS,
  SOURCE_ROOTS,
  SOURCE_URL,
  buildSourceOffer,
  listSourceFiles,
  renderSourcePage,
  sourceManifest,
};
