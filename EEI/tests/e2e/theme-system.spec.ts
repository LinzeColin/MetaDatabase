import { expect, test } from "@playwright/test";

// S9PAT01 deep-space design system: the theme attribute must be present
// before any client hydration (HEAD_INIT anti-flicker contract), themes must
// switch without a reload, and reduced-motion must collapse the motion scale.

test("theme is stamped before paint and defaults to deep-space", async ({ page }) => {
  await page.goto("/");
  const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
  expect(theme).toBe("deep-space");
  const bg = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()
  );
  expect(bg).toBe("#070b14");
});

test("stored daylight preference wins without flashing", async ({ browser }) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    window.localStorage.setItem("eei.theme.v1", "daylight");
  });
  const page = await context.newPage();
  await page.goto("/");
  const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
  expect(theme).toBe("daylight");
  const bg = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()
  );
  expect(bg).toBe("#f6f7f9");
  await context.close();
});

test("reduced-motion collapses the motion scale token", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/");
  const motionScale = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--motion-scale").trim()
  );
  expect(motionScale).toBe("0");
  await context.close();
});

// S9PBT01 V4 → P0-2：the legend inventory and the honest coverage badge
// （GAPS 黑话改为「供应链覆盖 X/16 环节」，无 API 时如实说未知）。
test("empire legend shows zone inventory and an honest coverage badge", async ({ page }) => {
  await page.goto("/");
  const legend = page.getByTestId("empire-legend");
  await expect(legend).toBeVisible();
  await expect(page.getByTestId("legend-zone-focus")).toContainText("焦点");
  const zoneRows = await legend.locator("li").count();
  expect(zoneRows).toBeGreaterThanOrEqual(4);
  // Without an API base the badge must say unknown - never a fabricated %.
  await expect(page.getByTestId("empire-gaps-badge")).toContainText("供应链覆盖");
  await expect(page.getByTestId("empire-gaps-badge")).toContainText("未知");
});

// S9PCT01 V3: honest history scrubber (no API -> no invented years).
test("history scrubber shows an honest empty state without an API", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("empire-history-scrubber")).toBeVisible();
  await expect(page.getByTestId("history-scrubber-empty")).toContainText("历史纵深暂不可用");
});

// S9PCT02 V7: the Ask bar reroots on in-graph names and assembles a
// ChatGPT context prompt otherwise (window.open stubbed, zero real nav).
test("ask bar reroots on entity names and marks chatgpt jumps", async ({ page }) => {
  await page.addInitScript(() => {
    window.open = () => null;
  });
  await page.goto("/");
  const askBar = page.getByTestId("ask-bar");
  await expect(askBar).toHaveAttribute("data-last-ask-action", "idle");
  await page.getByTestId("ask-bar-input").fill("cloud");
  await page.getByTestId("ask-bar-submit").click();
  await expect(askBar).toHaveAttribute("data-last-ask-action", /^reroot:/);
  await page.getByTestId("ask-bar-input").fill("这家公司的出口管制风险如何演变？");
  await page.getByTestId("ask-bar-submit").click();
  await expect(askBar).toHaveAttribute("data-last-ask-action", "chatgpt:new-chat");
});
