import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import {
  extractXhsLikesVisibleBatch,
  validateXhsLikesBatch,
} from "../src/xhs-likes.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/adapters/v1/xhs_likes/dom");
const manifest = JSON.parse(await readFile(join(FIXTURE_ROOT, "fixture_manifest.json"), "utf8"));

function requireCondition(condition, code) {
  if (!condition) throw new Error(code);
}

let browser;
let currentCase = "bootstrap";
try {
  browser = await chromium.launch({ channel: "chromium", headless: true });
  const page = await browser.newPage();
  const consoleErrors = [];
  const unexpectedRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push("console_error");
  });
  page.on("pageerror", () => consoleErrors.push("page_error"));
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() === "document") return route.continue();
    unexpectedRequests.push("blocked_non_document_request");
    return route.abort("blockedbyclient");
  });

  let ready = 0;
  let failures = 0;
  let totalItems = 0;
  let totalErrorEvidence = 0;
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
    const result = validateXhsLikesBatch(await page.evaluate(
      extractXhsLikesVisibleBatch,
      { maxItems: 20, ownerGesture: true, scopeMode: fixtureCase.scope_mode },
    ));
    requireCondition(result.status === fixtureCase.expected.status, "status_mismatch");
    requireCondition(result.batch.completion_signal === fixtureCase.expected.completion_signal, "completion_mismatch");
    requireCondition(result.items.length === fixtureCase.expected.items, "item_count_mismatch");
    requireCondition(result.errors.length === fixtureCase.expected.errors, "error_count_mismatch");
    requireCondition(result.batch.automatic_scroll === false, "automatic_scroll");
    requireCondition(result.batch.explicit_owner_action === true, "owner_action");
    requireCondition(!/\b(?:cookie|download_url|html|media_url|raw_dom|src|token)\b/iu.test(JSON.stringify(result)), "unsafe_surface");
    if (result.status === "ready") ready += 1;
    else failures += 1;
    totalItems += result.items.length;
    totalErrorEvidence += result.errors.length;
    await page.unroute(routedUrl.href);
  }
  requireCondition(consoleErrors.length === 0, "console_errors");
  requireCondition(unexpectedRequests.length === 0, "unexpected_network_requests");
  process.stdout.write(`${JSON.stringify({
    automatic_scrolls: 0,
    console_uncaught_errors: 0,
    error_evidence: totalErrorEvidence,
    fixture_cases: manifest.cases.length,
    identified_items: totalItems,
    network_calls: unexpectedRequests.length,
    owner_canary: "NOT_RUN",
    platform_calls: 0,
    ready_cases: ready,
    rejected_or_partial_cases: failures,
    status: "PASS",
  })}\n`);
} catch (error) {
  process.stderr.write(`${JSON.stringify({ code: `fixture_${currentCase}`, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
