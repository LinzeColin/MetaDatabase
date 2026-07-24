import { expect, test, type Page } from "@playwright/test";

// T1118 / A167: visual regression baselines for approved workspace states.
// Baselines are CI-authoritative (ubuntu-latest font stack); the suite runs
// on Linux only because macOS/Windows font metrics shift CJK glyph widths
// and would demand a per-platform baseline set nobody reviews. Screenshots
// are viewport-sized (1440x900 above-the-fold), animations disabled so the
// empire-canvas pulse/draw-in choreography cannot drift pixels between runs.
const LINUX_ONLY = process.platform !== "linux";

const SCREENSHOT_OPTIONS = {
  animations: "disabled" as const,
  caret: "hide" as const,
  maxDiffPixelRatio: 0.02
};

async function settle(page: Page): Promise<void> {
  await page.getByTestId("ecosystem-map-surface").waitFor({ state: "visible" });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(resolve))
    );
  });
  await page.waitForTimeout(400);
}

test.describe("A167 approved workspace states", () => {
  test.skip(LINUX_ONLY, "CI-authoritative Linux baselines");

  test("captures approved default state", async ({ page }) => {
    await page.goto("/");
    await settle(page);
    await expect(page).toHaveScreenshot("approved-default.png", SCREENSHOT_OPTIONS);
  });

  test("captures lens pivot state", async ({ page }) => {
    await page.goto("/");
    await settle(page);
    // Retry-click: a click landing before hydration is a silent no-op on
    // slow runners, so each attempt re-clicks until the state contract
    // confirms the handler actually ran.
    await expect(async () => {
      await page.getByTestId("lens-capital_transactions").click();
      await expect(page).toHaveURL(/lens=capital_transactions/, { timeout: 1500 });
    }).toPass({ timeout: 20_000 });
    await settle(page);
    await expect(page).toHaveScreenshot("approved-lens-pivot.png", SCREENSHOT_OPTIONS);
  });

  test("captures grouped dense list state", async ({ page }) => {
    await page.goto("/");
    await settle(page);
    await expect(async () => {
      await page.getByTestId("zoom-L0").click();
      await expect(page.getByTestId("workspace-shell")).toHaveAttribute(
        "data-semantic-zoom",
        "L0",
        { timeout: 1500 }
      );
    }).toPass({ timeout: 20_000 });
    await settle(page);
    await expect(page).toHaveScreenshot("approved-dense-list.png", SCREENSHOT_OPTIONS);
  });

  test("captures empty search result state", async ({ page }) => {
    await page.goto("/");
    await settle(page);
    await expect(async () => {
      await page.getByTestId("global-search-input").fill("zzz-no-such-entity");
      await expect(page.getByTestId("global-search-results")).toBeEmpty({ timeout: 1500 });
    }).toPass({ timeout: 20_000 });
    await expect(page).toHaveScreenshot("approved-empty-search.png", SCREENSHOT_OPTIONS);
  });

  test("captures loading state while APIs stay pending", async ({ page }) => {
    // Stall every backend call: the workspace must stay usable on fixture
    // data with the context badge in its pre-resolution state (no skeleton
    // flash, no fabricated freshness).
    await page.route("**/v1/**", () => {
      /* never fulfilled */
    });
    await page.goto("/");
    await settle(page);
    await expect(page).toHaveScreenshot("approved-loading-pending.png", SCREENSHOT_OPTIONS);
  });

  test("captures error state when APIs fail", async ({ page }) => {
    // The family-module shell renders the analysis-context badge (the home
    // canvas has its own context panel instead); with the API 500-routed —
    // or absent, as on CI — it must show the amber fallback label instead
    // of fabricating live context.
    // P2-10: /ma now redirects to /capital; the surviving family-module surface
    // is /signals ("战略信号" tab), which renders the same shared panel + badge.
    // NOTE: this changes the captured page, so approved-error-api-*.png must be
    // re-recorded on the Linux CI baseline job (A167) — the shell layout differs.
    await page.route("**/v1/**", (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: "{}" })
    );
    await page.goto("/signals");
    await expect(page.getByTestId("context-fallback")).toBeVisible();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve))
      );
    });
    await page.waitForTimeout(400);
    await expect(page).toHaveScreenshot("approved-error-api.png", SCREENSHOT_OPTIONS);
  });
});
