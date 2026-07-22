import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import {
  buildWeiboCapturePayload,
  extractWeiboCurrentPage,
  validateWeiboPageFacts,
} from "../src/weibo-current-page.js";
import { recognizePage } from "../src/page-support.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/weibo_current_page");
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

function exactObject(actual, expected) {
  return Object.keys(actual).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => actual[key] === value);
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
  let blockedPlatformNetworkRequests = 0;
  let fixtureDocumentsFulfilled = 0;
  let platformRequestsObserved = 0;
  for (const fixtureCase of manifest.cases) {
    currentCase = fixtureCase.id;
    const html = await readFile(join(FIXTURE_ROOT, fixtureCase.file), "utf8");
    requireCondition(!/<(?:form|iframe|script)\b/iu.test(html), "active_fixture_markup");
    requireCondition(!/\b(?:poster|src|srcset)\s*=/iu.test(html), "media_fixture_attribute");
    requireCondition(!/url\s*\(/iu.test(html), "css_url_fixture");
    const routedUrl = new URL(fixtureCase.page_url);
    routedUrl.hash = "";
    await page.route("**/*", (route) => {
      const requestUrl = new URL(route.request().url());
      requestUrl.hash = "";
      const platformRequest = new Set(["weibo.com", "www.weibo.com"]).has(
        requestUrl.hostname.toLowerCase(),
      );
      if (platformRequest) platformRequestsObserved += 1;
      if (
        requestUrl.href === routedUrl.href
        && route.request().isNavigationRequest()
        && route.request().resourceType() === "document"
      ) {
        fixtureDocumentsFulfilled += 1;
        return route.fulfill({
          body: html,
          contentType: "text/html; charset=utf-8",
          status: 200,
        });
      }
      if (platformRequest) blockedPlatformNetworkRequests += 1;
      return route.abort("blockedbyclient");
    });
    await page.goto(fixtureCase.page_url, { waitUntil: "domcontentloaded" });
    const facts = validateWeiboPageFacts(await page.evaluate(extractWeiboCurrentPage));
    const expected = fixtureCase.expected;
    if (facts.status !== expected.status) observationDiffMismatches += 1;
    if (expected.status === "ready") {
      if (
        facts.page_context.content_id !== expected.content_id
        || facts.page_context.content_type !== expected.content_type
        || facts.page_context.title !== expected.title
        || facts.page_url !== expected.page_url
      ) observationDiffMismatches += 1;
      const canonical = new URL(facts.page_url);
      if (canonical.search || canonical.hash) queryFragmentPersisted += 1;
      requireCondition(canonical.hostname === "www.weibo.com", "canonical_host");
      requireCondition(canonical.pathname === `/detail/${expected.content_id}`, "canonical_path");
      const payload = buildWeiboCapturePayload(facts);
      requireCondition(
        payload.auto_scroll === false
          && payload.change_account_state === false
          && payload.category_id === null
          && payload.user_gesture === true,
        "capture_policy_flags",
      );
      stableIdsVerified += 1;
    } else {
      if (facts.code !== "X2N_PLATFORM_CHANGED" || facts.reason !== expected.reason) {
        observationDiffMismatches += 1;
      }
      platformChangedVerified += 1;
    }
    const rendered = JSON.stringify(facts);
    requireCondition(
      !/\b(?:href|html|media|preview_url|raw_dom|redirect_url|src|srcset)\b/iu.test(rendered),
      "raw_media_or_preview_surface",
    );
    await page.unroute("**/*");
  }

  let policyCasesVerified = 0;
  let blockedBudgetCasesVerified = 0;
  for (const policyCase of manifest.policy_cases) {
    currentCase = policyCase.id;
    const result = recognizePage(policyCase.url);
    requireCondition(exactObject(result, policyCase.expected), "policy_state_diff");
    if (result.reason === "weibo_budget_zero_quota_unknown_disabled") blockedBudgetCasesVerified += 1;
    policyCasesVerified += 1;
  }

  let redirectSsrfRejections = 0;
  for (const redirectCase of manifest.redirect_ssrf_cases) {
    currentCase = redirectCase.id;
    const result = recognizePage(redirectCase.url);
    requireCondition(
      exactObject(result, {
        executable: false,
        platform: "weibo",
        reason: "weibo_arbitrary_url_control_rejected",
        supported: true,
      }),
      "redirect_ssrf_not_rejected",
    );
    redirectSsrfRejections += 1;
  }

  let schemaDriftRejections = 0;
  const validFacts = {
    page_context: {
      content_id: "synthetic-wb-status-validator-001",
      content_type: "text",
      title: "Synthetic validator title",
    },
    page_url: "https://www.weibo.com/detail/synthetic-wb-status-validator-001",
    platform: "weibo",
    provenance: {
      canonical_url: { source: "stable_mid", status: "derived" },
      content_id: { source: "location_path_and_status_surface", status: "observed_verified" },
      content_type: { source: "detail_text_marker", status: "observed" },
      title: { source: "detail_heading", status: "observed" },
    },
    schema_version: "1.0",
    status: "ready",
  };
  const invalidFacts = [
    { ...validFacts, preview_url: "synthetic-value" },
    { ...validFacts, redirect_url: "synthetic-value" },
    { ...validFacts, media_url: "synthetic-value" },
    {
      ...validFacts,
      page_context: { ...validFacts.page_context, content_id: "NrRealShape0" },
      page_url: "https://www.weibo.com/detail/NrRealShape0",
    },
    { ...validFacts, page_context: { ...validFacts.page_context, title: "https://media.invalid/value" } },
    { ...validFacts, page_url: `${validFacts.page_url}?url=synthetic-value` },
  ];
  for (const invalid of invalidFacts) {
    try {
      validateWeiboPageFacts(invalid);
    } catch {
      schemaDriftRejections += 1;
    }
  }
  try {
    buildWeiboCapturePayload(validateWeiboPageFacts({
      code: "X2N_PLATFORM_CHANGED",
      platform: "weibo",
      reason: "detail_surface_missing",
      schema_version: "1.0",
      status: "platform_changed",
    }));
  } catch {
    schemaDriftRejections += 1;
  }

  const platformCalls = platformRequestsObserved
    - fixtureDocumentsFulfilled
    - blockedPlatformNetworkRequests;
  requireCondition(observationDiffMismatches === 0, "observation_diff");
  requireCondition(queryFragmentPersisted === 0, "query_fragment_persistence");
  requireCondition(fixtureDocumentsFulfilled === manifest.cases.length, "fixture_document_count");
  requireCondition(platformCalls === 0, "platform_network_call");
  requireCondition(blockedPlatformNetworkRequests === 0, "unexpected_platform_request");
  requireCondition(policyCasesVerified === manifest.policy_cases.length, "policy_matrix");
  requireCondition(blockedBudgetCasesVerified === 2, "blocked_budget_matrix");
  requireCondition(redirectSsrfRejections === manifest.redirect_ssrf_cases.length, "redirect_ssrf_matrix");
  requireCondition(schemaDriftRejections === 7, "schema_drift_matrix");
  requireCondition(consoleErrors.length === 0, "console_errors");
  process.stdout.write(`${JSON.stringify({
    blocked_budget_cases_verified: blockedBudgetCasesVerified,
    blocked_platform_network_requests: blockedPlatformNetworkRequests,
    console_uncaught_errors: consoleErrors.length,
    fixture_cases: manifest.cases.length,
    fixture_documents_fulfilled: fixtureDocumentsFulfilled,
    observation_diff_mismatches: observationDiffMismatches,
    owner_canary: "NOT_RUN",
    platform_changed_verified: platformChangedVerified,
    platform_calls: platformCalls,
    platform_requests_observed: platformRequestsObserved,
    policy_cases_verified: policyCasesVerified,
    query_fragment_persisted: queryFragmentPersisted,
    redirect_ssrf_rejections: redirectSsrfRejections,
    schema_drift_rejections: schemaDriftRejections,
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
