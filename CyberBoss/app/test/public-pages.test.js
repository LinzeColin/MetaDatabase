"use strict";

// 「首页 boss 没有按钮跳转到 /join，而且二维码过期你没有刷新二维码的按钮，
//   不能永远确保长期持续稳定使用，我这是要市场化的产品。」
//
// 两条都是真的，而且是同一类毛病：**页面上存在走不出去的状态**。
//   · 根路径 302 跳 /admin —— 陌生人打开这个域名，撞在主人的登录墙上，
//     而"怎么开始用"没有任何入口。等于把大门开在员工通道上。
//   · 「换一张码」默认 hidden，只在 fetch 抛错时才露出来 —— 码静默失效的时候，
//     页面是一张看起来正常但已经死掉的图，加一个访客找不到的按钮。
//
// 这一份守的就是"任何时刻都有出路"。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

function template(name) {
  return fs.readFileSync(path.join(__dirname, "../templates", name), "utf8");
}

// ── 首页 ────────────────────────────────────────────────────

test("根路径给的是公开落地页，不是后台登录页", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/services/portal/portal-server.js"), "utf8",
  );

  assert.ok(
    !/ROOT_PATHS[\s\S]{0,200}Location:\s*"\/admin"/.test(source),
    "根路径又跳回 /admin 了——陌生人一进来就撞在登录墙上",
  );
  assert.match(source, /ROOT_PATHS\.includes\(pathname\)[\s\S]{0,400}HOME_TEMPLATE/);
});

test("首页有一个去 /join 的按钮，而且是最显眼的那个", () => {
  const html = template("home.html");

  assert.match(html, /href="\/join"/, "首页没有去扫码页的入口");
  // 主按钮在管理员入口前面出现：视觉顺序就是优先级。
  assert.ok(
    html.indexOf('href="/join"') < html.indexOf('href="/admin"'),
    "管理员入口排在了「开始用」前面",
  );
});

test("首页不含任何运营信息——它对所有人开放", () => {
  const html = template("home.html");

  for (const leak of ["额度", "用量", "人数", "token", "usage"]) {
    assert.ok(!html.includes(leak), `首页上出现了「${leak}」，这一页任何人都能打开`);
  }
});

// ── 扫码页 ──────────────────────────────────────────────────

test("「换一张码」永远看得见，不再是出错才露出来", () => {
  const html = template("join.html");

  assert.match(
    html,
    /<button id="again">/,
    "按钮又被加回 hidden 了——码静默失效时访客就没有出路了",
  );
});

test("不等服务端说过期，自己提前换", () => {
  const html = template("join.html");

  // 服务端那张票活 6 分钟，客户端 5 分钟就换：**永远赶在它被清掉之前**。
  const auto = html.match(/AUTO_REFRESH_MS\s*=\s*(\d+)\s*\*\s*60\s*\*\s*1000/);
  assert.ok(auto, "没有自动换新的定时器");
  assert.ok(
    Number(auto[1]) < 6,
    "自动换新比服务端 6 分钟的 TTL 还晚，等于没有兜底",
  );
  assert.match(html, /autoTimer\s*=\s*setTimeout\(mint/);
});

test("服务端认不出这张票，也当过期处理", () => {
  const html = template("join.html");

  // 只认 expired 的话，票被清掉之后状态接口回别的词，页面就永远停在死图上。
  assert.match(html, /state === "expired" \|\| state === "unknown" \|\| d\.ok === false/);
});

test("告诉访客这张码还能用多久——不然他不知道该等还是该换", () => {
  const html = template("join.html");

  assert.match(html, /id="ttl"/);
  assert.match(html, /后自动换新/);
});

test("扫成功之后倒计时和按钮都收起来，别让人再点一次", () => {
  const html = template("join.html");
  const confirmed = html.slice(html.indexOf('state === "confirmed"'));

  assert.match(confirmed.slice(0, 400), /el\("again"\)\.hidden = true/);
});

test("拿码失败时说清楚下一步，不是一句干巴巴的错误", () => {
  const html = template("join.html");

  assert.match(html, /点下面的按钮再试一次/);
});

// ── 两页都不许有外部依赖 ────────────────────────────────────

test("公开页不拉任何外部资源——CSP 是 default-src 'none'", () => {
  for (const name of ["home.html", "join.html"]) {
    const html = template(name);
    assert.ok(
      !/(src|href)="https?:\/\//.test(html),
      `${name} 引了外部资源，CSP 会把它挡掉，页面会缺件`,
    );
  }
});
