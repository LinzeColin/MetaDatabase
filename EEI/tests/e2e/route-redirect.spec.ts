import { expect, test } from "@playwright/test";

// P2-10 旧路由收编 e2e 契约（UX_SPEC_EEI v1.0 §A.3 / §G-P2-10）。
// 旧链接 0 死链：自动到新位置且高亮正确一级入口。静态导出用客户端 replace
// （RouteRedirect），dev 与 export 都走同一路径，故 dev 下同样可验证。

test("/ma redirects to capital with the M&A event filter", async ({ page }) => {
  await page.goto("/ma");
  await expect(page).toHaveURL(/\/capital\?event_type=ma/);
  // 高亮正确入口：资本与事件。
  await expect(page.getByTestId("main-nav-capital_network")).toHaveAttribute(
    "aria-current",
    "page"
  );
});

test("/control redirects to the structure control anchor", async ({ page }) => {
  await page.goto("/control");
  await expect(page).toHaveURL(/\/structure(#control)?$/);
  await expect(page.getByTestId("main-nav-group_structure")).toHaveAttribute(
    "aria-current",
    "page"
  );
});

test("/policy redirects to the external-signals policy tab", async ({ page }) => {
  await page.goto("/policy");
  await expect(page).toHaveURL(/\/signals\?tab=policy/);
  await expect(page.getByTestId("main-nav-strategic_signals")).toHaveAttribute(
    "aria-current",
    "page"
  );
  // 落地即选中政策 tab。
  await expect(page.getByTestId("policy-environment-page")).toBeVisible();
});

test("old route stays non-dead even without JS (meta-refresh)", async ({ page }) => {
  // 关掉 JS：客户端 replace 不执行，但 meta http-equiv=refresh（React 19 提升进
  // <head>）仍把浏览器带到新位置——静态导出无 server redirects 时的 0 死链保证。
  const context = await page.context().browser()!.newContext({ javaScriptEnabled: false });
  const noJsPage = await context.newPage();
  await noJsPage.goto("/ma");
  await expect(noJsPage).toHaveURL(/\/capital\?event_type=ma/);
  await context.close();
});

test("external-signals page carries both tabs and syncs the URL", async ({ page }) => {
  await page.goto("/signals");
  await expect(page.getByTestId("strategic-signals-page")).toBeVisible();
  // 默认战略信号 tab。
  await expect(page.getByTestId("signals-tab-signals")).toHaveAttribute("data-active", "true");
  await expect(page.getByTestId("signals-overview")).toBeVisible();

  // 切到政策 tab → 内容切换 + URL 同步。
  await page.getByTestId("signals-tab-policy").click();
  await expect(page.getByTestId("policy-environment-page")).toBeVisible();
  await expect(page).toHaveURL(/\/signals\?tab=policy/);
  await expect(page.getByTestId("signals-tab-policy")).toHaveAttribute("data-active", "true");
});

test("external-signals deep-links straight to the policy tab", async ({ page }) => {
  await page.goto("/signals?tab=policy");
  await expect(page.getByTestId("policy-environment-page")).toBeVisible();
  await expect(page.getByTestId("signals-tab-policy")).toHaveAttribute("data-active", "true");
});
