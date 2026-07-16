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

// S9PBT01 V4: the legend inventory and the honest GAPS badge.
test("empire legend shows zone inventory and an honest GAPS badge", async ({ page }) => {
  await page.goto("/");
  const legend = page.getByTestId("empire-legend");
  await expect(legend).toBeVisible();
  await expect(page.getByTestId("legend-zone-focus")).toContainText("焦点");
  const zoneRows = await legend.locator("li").count();
  expect(zoneRows).toBeGreaterThanOrEqual(4);
  // Without an API base the badge must say unknown - never a fabricated %.
  await expect(page.getByTestId("empire-gaps-badge")).toContainText("GAPS");
  await expect(page.getByTestId("empire-gaps-badge")).toContainText("未知");
});
