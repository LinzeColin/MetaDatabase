import { expect, test, type Page } from "@playwright/test";

// P2-11 响应式 e2e 契约（UX_SPEC_EEI v1.0 §G-P2-11）。
// <1280px 右栏收成可滑出抽屉；<768px 左栏变底部 dock（触控目标 ≥44px）；
// iPhone 视口（390px）核心流程无横向溢出。e2e 稳定性：等画布可见再量测，
// 点击类断言用 toPass 兜住水合前的空点。

const IPHONE = { width: 390, height: 844 };
const TABLET = { width: 900, height: 1000 };

async function noHorizontalOverflow(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.documentElement;
    // 允许 1px 亚像素误差；page 级横向滚动条即判失败。
    return el.scrollWidth <= el.clientWidth + 1;
  });
}

test.describe("iPhone 390px", () => {
  test.use({ viewport: IPHONE });

  test("home has no horizontal overflow and exposes the bottom dock", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
    expect(await noHorizontalOverflow(page)).toBe(true);
    // 底部 dock：主导航 + 全局工具（搜索 / 我的）均可达。
    await expect(page.getByTestId("main-nav-capital_network")).toBeVisible();
    await expect(page.getByTestId("command-search-trigger")).toBeVisible();
    await expect(page.getByTestId("my-drawer-trigger")).toBeVisible();
  });

  test("dock nav targets meet the 44px touch minimum", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
    const box = await page.getByTestId("main-nav-capital_network").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);
  });

  test("right column collapses into a toggleable evidence drawer", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
    const shell = page.getByTestId("workspace-shell");
    await expect(shell).toHaveAttribute("data-inspector-open", "false");
    const toggle = page.getByTestId("inspector-drawer-toggle");
    await expect(toggle).toBeVisible();
    await expect(async () => {
      await toggle.click();
      await expect(shell).toHaveAttribute("data-inspector-open", "true", { timeout: 800 });
    }).toPass({ timeout: 10000 });
    // 抽屉滑入视口（右栏左缘落在视宽内）。
    await expect
      .poll(async () => {
        const inspectorBox = await page.getByTestId("evidence-center").boundingBox();
        return inspectorBox ? inspectorBox.x : 9999;
      })
      .toBeLessThan(390);
    await page.getByTestId("inspector-drawer-close").click();
    await expect(shell).toHaveAttribute("data-inspector-open", "false");
  });

  test("capital events page has no horizontal overflow and stays navigable", async ({ page }) => {
    await page.goto("/capital");
    await page.getByTestId("capital-river-shell").waitFor({ state: "visible" });
    expect(await noHorizontalOverflow(page)).toBe(true);
    await expect(page.getByTestId("main-nav-business_map")).toBeVisible();
  });

  test("command search palette opens on mobile without overflow", async ({ page }) => {
    await page.goto("/");
    // dock 触发钮的可见性另有专测；此处用键盘唤起（避开 dev server 底部 Next
    // 调试浮层对底 dock 点击的拦截——静态导出无此浮层）。键盘监听水合较晚，
    // 用 toPass 重试（同 command-search.spec 的做法）。
    await expect(page.getByTestId("command-search-trigger")).toBeVisible();
    const overlay = page.getByTestId("command-search-overlay");
    await expect(async () => {
      if ((await overlay.count()) === 0) {
        await page.keyboard.press("Control+k");
      }
      await expect(overlay).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 15000 });
    // 弹层不撑破视口。
    expect(await noHorizontalOverflow(page)).toBe(true);
  });
});

test.describe("tablet 900px", () => {
  test.use({ viewport: TABLET });

  test("keeps the icon rail, drawers the right column, no overflow", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ecosystem-map-svg").waitFor({ state: "visible" });
    expect(await noHorizontalOverflow(page)).toBe(true);
    // <1280 仍走抽屉：开关可见，右栏默认收起。
    await expect(page.getByTestId("inspector-drawer-toggle")).toBeVisible();
    await expect(page.getByTestId("workspace-shell")).toHaveAttribute(
      "data-inspector-open",
      "false"
    );
  });
});
