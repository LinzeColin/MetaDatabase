import assert from "node:assert/strict";
import test from "node:test";

async function render(path, host = "localhost") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://${host}${path}`, { headers: { accept: "text/html", host } }),
    {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

const pages = {
  welcome: { route: "/?reference=welcome", required: ["welcome-page", "welcome-kitty", "welcome-enter"] },
  home: { route: "/?reference=home", required: ["sidebar", "home-time", "quote-card", "habit-grid"] },
  ledger: { route: "/?reference=ledger", required: ["sidebar", "summary-grid", "ledger-form", "record-list-card"] },
  "fatloss-food": { route: "/?reference=fatloss-food", required: ["sidebar", "module-tabs", "food-card", "upload-zone"] },
  period: { route: "/?reference=period", required: ["sidebar", "period-form", "period-overview", "period-history"] },
};

test("five fixed reference routes render the frozen structure without account chrome", async () => {
  for (const [name, spec] of Object.entries(pages)) {
    const response = await render(spec.route);
    assert.equal(response.status, 200, name);
    const html = await response.text();
    assert.match(html, new RegExp(`data-reference-page=\"${name}\"`), name);
    assert.match(html, /data-reference-mode="true"/, name);
    assert.doesNotMatch(html, /class="account-entry/, name);
    assert.doesNotMatch(html, /codex-preview|Building your site|react-loading-skeleton/i, name);
    for (const className of spec.required) {
      assert.match(html, new RegExp(`class=\"[^\"]*${className}`), `${name}: ${className}`);
    }
  }
});

test("normal routes retain a separate account entry and resolve without reference mode", async () => {
  const [home, auth] = await Promise.all([render("/?view=home"), render("/auth/sign-in")]);
  assert.equal(home.status, 200);
  const homeHtml = await home.text();
  assert.match(homeHtml, /class="account-entry normal-only"/);
  assert.match(homeHtml, /data-account-state="signed-out"/);
  assert.match(homeHtml, /登录以同步/);
  assert.doesNotMatch(homeHtml, /正在确认登录…/);
  assert.match(homeHtml, /href="\/auth\/sign-in"/);
  assert.match(homeHtml, /aria-label="个人日程导航"/);
  assert.doesNotMatch(homeHtml, /返回工作台/);
  assert.match(homeHtml, /data-reference-mode="false"/);
  assert.equal(auth.status, 200);
  const authHtml = await auth.text();
  assert.match(authHtml, /欢迎回来/);
  assert.match(authHtml, /aria-label="返回个人日程"/);
  assert.doesNotMatch(authHtml, /返回工作台/);
});

test("the retired domain renders a non-interactive handoff before workbench controls", async () => {
  const response = await render("/?view=home", "huchuliang-workbench.linzezhang35.chatgpt.site");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /class="legacy-domain-transfer"/);
  assert.match(html, /正在打开个人日程/);
  assert.match(html, /href="https:\/\/mydairy\.linzezhang\.com"/);
});

test("account entry reports session state without rendering account identity", async () => {
  const { readFile } = await import("node:fs/promises");
  const [source, serverEntry] = await Promise.all([
    readFile(new URL("../app/_components/workbench/account-entry.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/_components/workbench/account-entry-server.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(source, /get-session\?disableCookieCache=true/);
  assert.match(source, /addEventListener\("focus", refresh\)/);
  assert.match(source, /addEventListener\("pageshow", refresh\)/);
  assert.match(source, /addEventListener\("visibilitychange", refreshWhenDocumentVisible\)/);
  assert.match(source, /accountEntryInitialStateForSession/);
  assert.match(serverEntry, /api\.getSession\(\{/);
  assert.match(serverEntry, /disableCookieCache: true/);
  assert.match(source, /登录以同步/);
  assert.match(source, /已登录 · 账户/);
  assert.match(source, /已登录 · 待验证/);
  assert.doesNotMatch(serverEntry, /user\.email|user\.name/);
});
