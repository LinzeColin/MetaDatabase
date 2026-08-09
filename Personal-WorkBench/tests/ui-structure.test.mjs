import assert from "node:assert/strict";
import test from "node:test";

async function render(path) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
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
  assert.match(homeHtml, /登录 \/ 账户/);
  assert.match(homeHtml, /href="\/account"/);
  assert.match(homeHtml, /data-reference-mode="false"/);
  assert.equal(auth.status, 200);
  assert.match(await auth.text(), /欢迎回来/);
});
