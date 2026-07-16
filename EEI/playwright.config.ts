import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: ["saved-view-live.spec.ts"],
  timeout: 30_000,
  // CI runners intermittently exceed the old 5s budget on data-hydration
  // assertions (capital-river A110 flaked on an identical commit and greened
  // on rerun, 2026-07-16); widen the budget - no retries, specs are stateful.
  expect: {
    timeout: 10_000
  },
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }
    }
  ],
  webServer: {
    command: "npx --yes pnpm@11.8.0 --filter @eei/web dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000
  }
});
