import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PWB_BASE_URL || "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./tests/vps3",
  testMatch: ["ui-inventory.spec.ts", "two-account.spec.ts"],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "vps3-acceptance-output/results.json" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-360", use: { ...devices["Galaxy S9+"] } },
  ],
});
