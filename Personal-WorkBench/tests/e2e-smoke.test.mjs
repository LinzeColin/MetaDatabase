import assert from "node:assert/strict";
import test from "node:test";

async function render(path) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
      method: "GET",
    }),
    {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

const expectedReferenceRoutes = ["home", "ledger", "fatloss-food", "period"];
const expectedViewRoutes = ["home", "todo", "schedule", "diary", "savings", "anniversary"];

test("e2e smoke: frozen reference routes stay renderable", async () => {
  for (const route of expectedReferenceRoutes) {
    const response = await render(`/?reference=${route}`);
    assert.equal(response.status, 200, route);
    const html = await response.text();
    assert.match(html, new RegExp(`data-reference-page=\"${route}\"`), route);
    assert.match(html, /class=\"sidebar\"/);
    assert.match(html, /class=\"nav-list\"/);
    if (route === "home") {
      assert.match(html, /class=\"home-time\">11:27<\/div>/);
      assert.match(html, /class=\"home-date\">2026年8月2日<\/p>/);
    }
  }

  for (const route of expectedViewRoutes) {
    const response = await render(`/?view=${route}`);
    assert.equal(response.status, 200, route);
    const html = await response.text();
    assert.match(html, /class=\"app-stage/);
    assert.match(html, /data-reference-mode=\"false\"/);
    assert.match(html, /class=\"account-entry normal-only\"/);
  }
});

test("e2e smoke: normal mode carries account entry and no reference-only lock", async () => {
  const [home, auth, welcome] = await Promise.all([render("/?view=home"), render("/auth/sign-in"), render("/")]);
  assert.equal(home.status, 200);
  assert.equal(auth.status, 200);
  assert.equal(welcome.status, 200);
  const homeHtml = await home.text();
  const authHtml = await auth.text();
  const welcomeHtml = await welcome.text();
  assert.match(homeHtml, /class=\"account-entry normal-only\"/);
  assert.match(homeHtml, /href=\"\/account\"/);
  assert.match(homeHtml, /data-reference-mode=\"false\"/);
  assert.match(homeHtml, /正在读取本地时间…/);
  assert.doesNotMatch(homeHtml, /class=\"home-time\">11:27<\/div>/);
  assert.match(welcomeHtml, /正在读取本地日期…/);
  assert.match(authHtml, /欢迎回来/);
});

test("e2e smoke: every primary menu route renders its own normal-mode content", async () => {
  const routes = [
    ["home", "每日打卡"],
    ["todo", "待办列表"],
    ["ledger", "记账本"],
    ["fatloss-food", "减脂记录"],
    ["schedule", "日程安排"],
    ["anniversary", "纪念日"],
    ["diary", "日记"],
    ["savings", "存钱计划"],
    ["period", "经期记录"],
  ];

  for (const [route, distinctiveText] of routes) {
    const response = await render(`/?view=${route}`);
    assert.equal(response.status, 200, route);
    const html = await response.text();
    assert.match(html, new RegExp(distinctiveText), route);
    assert.match(html, /data-reference-mode="false"/, route);
  }
});

test("e2e smoke: email verification recovery and sign-in status guidance render", async () => {
  const [verification, verifiedSignIn, signedOutSignIn] = await Promise.all([
    render("/auth/verify-email"),
    render("/auth/sign-in?verified=1"),
    render("/auth/sign-in?signed_out=1"),
  ]);
  assert.equal(verification.status, 200);
  assert.equal(verifiedSignIn.status, 200);
  assert.equal(signedOutSignIn.status, 200);

  const verificationHtml = await verification.text();
  const verifiedSignInHtml = await verifiedSignIn.text();
  const signedOutSignInHtml = await signedOutSignIn.text();
  assert.match(verificationHtml, /验证邮箱/);
  assert.match(verificationHtml, /重新发送验证邮件/);
  assert.match(verifiedSignInHtml, /邮箱已验证，请登录。/);
  assert.match(signedOutSignInHtml, /已退出登录。/);
});
