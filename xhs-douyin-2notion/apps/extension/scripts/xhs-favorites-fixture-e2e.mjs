import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import {
  extractXhsFavoritesVisibleBatch,
  validateXhsFavoritesBatch,
} from "../src/xhs-favorites.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/adapters/v1/xhs_favorites/dom");
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
  let ownerMvpModeCases = 0;
  let readySample = null;
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
    const result = validateXhsFavoritesBatch(await page.evaluate(
      extractXhsFavoritesVisibleBatch,
      { maxItems: 20, ownerGesture: true, scopeMode: fixtureCase.scope_mode },
    ));
    requireCondition(result.status === fixtureCase.expected.status, "status_mismatch");
    requireCondition(result.batch.completion_signal === fixtureCase.expected.completion_signal, "completion_mismatch");
    requireCondition(result.items.length === fixtureCase.expected.items, "item_count_mismatch");
    requireCondition(result.errors.length === fixtureCase.expected.errors, "error_count_mismatch");
    requireCondition(result.batch.automatic_scroll === false, "automatic_scroll");
    requireCondition(result.batch.explicit_owner_action === true, "owner_action");
    requireCondition(!/\b(?:cookie|download_url|html|media_url|raw_dom|src|token)\b/iu.test(JSON.stringify(result)), "unsafe_surface");
    if (result.status === "ready") {
      ready += 1;
      readySample ??= JSON.parse(JSON.stringify(result));
      const ownerMvpResult = validateXhsFavoritesBatch(await page.evaluate(
        extractXhsFavoritesVisibleBatch,
        { maxItems: 20, ownerGesture: true, scopeMode: "owner_mvp_20" },
      ));
      requireCondition(ownerMvpResult.status === "ready", "owner_mvp_mode_rejected");
      requireCondition(ownerMvpResult.batch.automatic_scroll === false, "owner_mvp_automatic_scroll");
      ownerMvpModeCases += 1;
    }
    else failures += 1;
    totalItems += result.items.length;
    totalErrorEvidence += result.errors.length;
    await page.unroute(routedUrl.href);
  }
  requireCondition(readySample !== null, "missing_ready_validator_sample");
  const validPartial = JSON.parse(JSON.stringify(readySample));
  validPartial.status = "partial";
  validPartial.code = "X2N_PROVENANCE_INCOMPLETE";
  validPartial.batch.completion_signal = "unknown";
  validPartial.batch.visible_card_count = 2;
  validPartial.items = validPartial.items.slice(0, 1);
  validPartial.errors = [{ card_index: 1, code: "X2N_PROVENANCE_INCOMPLETE" }];
  validateXhsFavoritesBatch(validPartial);
  const invalidEnvelopes = [
    { ...validPartial, code: "X2N_PLATFORM_CHANGED" },
    { ...validPartial, errors: [{ card_index: 2, code: "X2N_PROVENANCE_INCOMPLETE" }] },
    {
      ...validPartial,
      errors: [
        { card_index: 1, code: "X2N_PROVENANCE_INCOMPLETE" },
        { card_index: 1, code: "X2N_PROVENANCE_INCOMPLETE" },
      ],
    },
    { ...validPartial, collection: { id: "collection_invalid", name_private: null, status: "observed" } },
  ];
  for (const candidate of invalidEnvelopes) {
    let rejected = false;
    try {
      validateXhsFavoritesBatch(candidate);
    } catch {
      rejected = true;
    }
    requireCondition(rejected, "validator_negative_case_accepted");
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
    owner_mvp_mode_cases: ownerMvpModeCases,
    platform_calls: 0,
    ready_cases: ready,
    rejected_or_partial_cases: failures,
    status: "PASS",
    validator_negative_cases: invalidEnvelopes.length,
  })}\n`);
} catch (error) {
  process.stderr.write(`${JSON.stringify({ code: `fixture_${currentCase}`, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
