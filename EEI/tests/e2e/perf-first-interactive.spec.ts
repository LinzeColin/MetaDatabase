import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

// T1119 / A168: fixture first-interactive-graph P75 must stay under 2.5s,
// and the raw samples must be recorded (annotation + JSON artifact) so the
// budget is auditable instead of a green checkmark with no numbers.
const SAMPLE_COUNT = 7;
const P75_BUDGET_MS = 2500;

test("A168 first interactive graph P75 under budget with recorded metrics", async ({ browser }, testInfo) => {
  test.setTimeout(120_000);

  // Warm-up: the dev server compiles the page on first hit; that cost is
  // build tooling, not product first-paint, so it stays out of the samples.
  {
    const warmup = await browser.newPage();
    await warmup.goto("/");
    await warmup.getByTestId("ecosystem-map-surface").waitFor({ state: "visible" });
    await warmup.close();
  }

  const samples: number[] = [];
  for (let index = 0; index < SAMPLE_COUNT; index += 1) {
    const page = await browser.newPage();
    await page.goto("/");
    await page.getByTestId("ecosystem-map-surface").waitFor({ state: "visible" });
    await page.getByTestId("zoom-L3").waitFor({ state: "visible" });
    const elapsedMs = await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve))
      );
      return performance.now();
    });
    samples.push(Math.round(elapsedMs));
    await page.close();
  }

  const sorted = [...samples].sort((a, b) => a - b);
  const p75 = sorted[Math.ceil(sorted.length * 0.75) - 1];
  const metrics = {
    metric: "first_interactive_graph_ms",
    samples,
    p75,
    budget_ms: P75_BUDGET_MS,
    sampled_at: new Date().toISOString(),
    platform: process.platform,
    ci: Boolean(process.env.CI)
  };

  testInfo.annotations.push({ type: "perf-first-interactive", description: JSON.stringify(metrics) });
  const outPath = join(testInfo.outputDir, "..", "perf-first-interactive.json");
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, JSON.stringify(metrics, null, 2));

  expect(p75, `P75 ${p75}ms over budget; samples=${samples.join(",")}`).toBeLessThan(
    P75_BUDGET_MS
  );
});
