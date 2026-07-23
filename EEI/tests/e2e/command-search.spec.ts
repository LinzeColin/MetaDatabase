import { expect, test } from "@playwright/test";

// P1-5 全局搜索 Cmd+K（UX_SPEC_EEI v1.0 §C.1）e2e 契约。
// 本机 dev 无生产 API：给 command-search 注入一个 localStorage API base 并
// mock /v1/entities，验证「唤起 → 输入 → 结果 → Enter 落地 / Esc 关闭」全链。

const MOCK_ENTITY_ID = "11111111-2222-4333-8444-555566667777";

async function mockEntities(page: import("@playwright/test").Page): Promise<void> {
  // command-search 读 localStorage 的 API base（eei.apiBaseUrl.v1）；指向同源
  // dev origin，请求在到达服务器前被 page.route 截获。
  await page.addInitScript(() => {
    window.localStorage.setItem("eei.apiBaseUrl.v1", "http://127.0.0.1:3000");
  });
  await page.route("**/v1/entities**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "nvi",
        entities: [
          {
            id: MOCK_ENTITY_ID,
            canonical_name: "NVIDIA Corporation",
            entity_type: "legal_entity",
            status: "published"
          }
        ]
      })
    })
  );
}

test("Cmd+K opens the command palette on any page", async ({ page }) => {
  await mockEntities(page);
  await page.goto("/supply-chain");
  const overlay = page.getByTestId("command-search-overlay");
  await expect(overlay).toHaveCount(0);
  // The global keydown listener attaches in a mount effect; pressing Control+K
  // before hydration finished (slow CI) dropped the keystroke and the overlay
  // never opened. Wait for the search trigger to hydrate, then retry the press
  // until the overlay is open — guarded on count so a hotkey that toggles is
  // never double-fired (which would close an overlay that just opened).
  // 监听 ctrlKey||metaKey + K；Linux CI 用 Control，mac 本机同样命中 ctrlKey 分支。
  await expect(page.getByTestId("command-search-trigger")).toBeVisible();
  await expect(async () => {
    if ((await overlay.count()) === 0) {
      await page.keyboard.press("Control+k");
    }
    await expect(overlay).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 15000 });
  await expect(page.getByTestId("command-search-input")).toBeFocused();
});

test("typing yields grouped results and Enter lands on the graph", async ({ page }) => {
  await mockEntities(page);
  await page.goto("/");
  await page.getByTestId("command-search-trigger").click();
  const input = page.getByTestId("command-search-input");
  await input.fill("nvi");
  const result = page.getByTestId(`command-search-result-${MOCK_ENTITY_ID}`);
  // 输入→结果（含 150ms 防抖）应在 400ms 量级内出现。
  await expect(result).toBeVisible({ timeout: 2000 });
  await expect(result).toContainText("NVIDIA Corporation");
  await input.press("Enter");
  await expect(page).toHaveURL(new RegExp(`subject=${MOCK_ENTITY_ID}`));
});

test("no-results state shows the honest b-type copy", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("eei.apiBaseUrl.v1", "http://127.0.0.1:3000");
  });
  await page.route("**/v1/entities**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ query: "zzz", entities: [] })
    })
  );
  await page.goto("/");
  await page.getByTestId("command-search-trigger").click();
  await page.getByTestId("command-search-input").fill("zzzzz");
  const empty = page.getByTestId("command-search-no-results");
  await expect(empty).toBeVisible({ timeout: 2000 });
  await expect(empty).toContainText("没找到");
  await expect(empty).toHaveAttribute("role", "alert");
});

test("Escape closes the palette", async ({ page }) => {
  await mockEntities(page);
  await page.goto("/");
  await page.getByTestId("command-search-trigger").click();
  await expect(page.getByTestId("command-search-overlay")).toBeVisible();
  await page.getByTestId("command-search-input").press("Escape");
  await expect(page.getByTestId("command-search-overlay")).toHaveCount(0);
});
