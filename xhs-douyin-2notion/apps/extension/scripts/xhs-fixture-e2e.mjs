import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import { extractXhsCurrentPage, validateXhsPageFacts } from "../src/xhs-current-page.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/xhs_current_page");
const manifest = JSON.parse(await readFile(join(FIXTURE_ROOT, "fixture_manifest.json"), "utf8"));

class FixtureFailure extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function requireCondition(condition, code) {
  if (!condition) throw new FixtureFailure(code);
}

let browser;
let currentCase = "bootstrap";
try {
  browser = await chromium.launch({ channel: "chromium", headless: true });
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push("console_error");
  });
  page.on("pageerror", () => consoleErrors.push("page_error"));

  let stableIdsVerified = 0;
  let platformChangedVerified = 0;
  let observationDiffMismatches = 0;
  let queryFragmentPersisted = 0;
  for (const fixtureCase of manifest.cases) {
    currentCase = fixtureCase.id;
    const html = await readFile(join(FIXTURE_ROOT, fixtureCase.file), "utf8");
    const routedUrl = new URL(fixtureCase.page_url);
    routedUrl.hash = "";
    await page.route(routedUrl.href, (route) => route.fulfill({
      body: html,
      contentType: "text/html; charset=utf-8",
      status: 200,
    }));
    await page.goto(fixtureCase.page_url, { waitUntil: "domcontentloaded" });
    const facts = validateXhsPageFacts(await page.evaluate(extractXhsCurrentPage));
    const expected = fixtureCase.expected;
    if (facts.status !== expected.status) observationDiffMismatches += 1;
    if (expected.status === "ready") {
      if (
        facts.page_context.content_id !== expected.content_id
        || facts.page_context.content_type !== expected.content_type
        || facts.page_context.title !== expected.title
      ) observationDiffMismatches += 1;
      const canonical = new URL(facts.page_url);
      if (canonical.search || canonical.hash || facts.page_url.includes("tracking=")) queryFragmentPersisted += 1;
      requireCondition(canonical.hostname === "www.xiaohongshu.com", "canonical_host");
      requireCondition(canonical.pathname === `/explore/${expected.content_id}`, "canonical_path");
      stableIdsVerified += 1;
    } else {
      if (facts.code !== "X2N_PLATFORM_CHANGED" || facts.reason !== expected.reason) {
        observationDiffMismatches += 1;
      }
      platformChangedVerified += 1;
    }
    const rendered = JSON.stringify(facts);
    requireCondition(!/\b(?:href|html|media|raw_dom|src)\b/iu.test(rendered), "raw_or_media_surface");
    await page.unroute(routedUrl.href);
  }
  requireCondition(observationDiffMismatches === 0, "observation_diff");
  requireCondition(queryFragmentPersisted === 0, "query_fragment_persistence");
  requireCondition(consoleErrors.length === 0, "console_errors");
  process.stdout.write(`${JSON.stringify({
    console_uncaught_errors: consoleErrors.length,
    fixture_cases: manifest.cases.length,
    observation_diff_mismatches: observationDiffMismatches,
    owner_canary: "NOT_RUN",
    platform_changed_verified: platformChangedVerified,
    platform_calls: 0,
    query_fragment_persisted: queryFragmentPersisted,
    stable_ids_verified: stableIdsVerified,
    status: "PASS",
  })}\n`);
} catch (error) {
  const code = error instanceof FixtureFailure ? error.code : `unexpected_${currentCase}`;
  process.stderr.write(`${JSON.stringify({ code, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
