import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PWB_BASE_URL || "http://127.0.0.1:3000";
const productionAcceptance = process.env.PWB_PRODUCTION_ACCEPTANCE === "1";
const acceptancePhase = process.env.PWB_ACCEPTANCE_PHASE || (productionAcceptance ? "production" : "public");

export default defineConfig({
  testDir: "./tests/vps3",
  testMatch: productionAcceptance
    ? ["two-account.spec.ts", "redeploy-persistence.spec.ts"]
    : ["ui-inventory.spec.ts"],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: productionAcceptance ? 1 : undefined,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: `vps3-acceptance-output/${acceptancePhase}-results.json` }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: productionAcceptance
    ? [{ name: "production-desktop", use: { ...devices["Desktop Chrome"] } }]
    : [
      { name: "desktop", use: { ...devices["Desktop Chrome"] } },
      { name: "mobile-360", use: { ...devices["Galaxy S9+"] } },
    ],
});
