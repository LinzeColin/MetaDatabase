import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import {
  buildBilibiliCapturePayload,
  extractBilibiliCurrentPage,
  validateBilibiliPageFacts,
} from "../src/bilibili-current-page.js";
import { recognizePage } from "../src/page-support.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/bilibili_current_page");
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
      const platformRequest = new Set(["bilibili.com", "www.bilibili.com"]).has(
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
    const facts = validateBilibiliPageFacts(await page.evaluate(extractBilibiliCurrentPage));
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
      if (canonical.search || canonical.hash || facts.page_url.includes("tracking=")) queryFragmentPersisted += 1;
      requireCondition(canonical.hostname === "www.bilibili.com", "canonical_host");
      requireCondition(
        canonical.pathname === `/video/${expected.content_id}`
          || canonical.pathname === `/read/${expected.content_id}`,
        "canonical_path",
      );
      stableIdsVerified += 1;
    } else {
      if (facts.code !== "X2N_PLATFORM_CHANGED" || facts.reason !== expected.reason) {
        observationDiffMismatches += 1;
      }
      platformChangedVerified += 1;
    }
    const rendered = JSON.stringify(facts);
    requireCondition(!/\b(?:href|html|media|raw_dom|src|srcset)\b/iu.test(rendered), "raw_or_media_surface");
    await page.unroute("**/*");
  }

  let policyCasesVerified = 0;
  for (const policyCase of manifest.policy_cases) {
    currentCase = policyCase.id;
    const result = recognizePage(policyCase.url);
    requireCondition(exactObject(result, policyCase.expected), "policy_state_diff");
    policyCasesVerified += 1;
  }

  let schemaDriftRejections = 0;
  const validFacts = {
    page_context: {
      content_id: "synthetic-bili-video-validator-001",
      content_type: "video",
      title: "Synthetic validator title",
    },
    page_url: "https://www.bilibili.com/video/synthetic-bili-video-validator-001",
    platform: "bilibili",
    provenance: {
      canonical_url: { source: "stable_content_id_and_page_kind", status: "derived" },
      content_id: { source: "location_path_and_detail_surface", status: "observed_verified" },
      content_type: { source: "detail_video_marker", status: "observed" },
      title: { source: "detail_heading", status: "observed" },
    },
    schema_version: "1.0",
    status: "ready",
  };
  const invalidFacts = [
    { ...validFacts, unexpected: true },
    { ...validFacts, page_context: { ...validFacts.page_context, content_type: "article" } },
    {
      ...validFacts,
      page_context: { ...validFacts.page_context, content_id: "BV1RealShape0" },
      page_url: "https://www.bilibili.com/video/BV1RealShape0",
    },
    { ...validFacts, page_context: { ...validFacts.page_context, title: "https://media.invalid/value" } },
  ];
  for (const invalid of invalidFacts) {
    try {
      validateBilibiliPageFacts(invalid);
    } catch {
      schemaDriftRejections += 1;
    }
  }
  try {
    buildBilibiliCapturePayload(validateBilibiliPageFacts({
      code: "X2N_PLATFORM_CHANGED",
      platform: "bilibili",
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
  requireCondition(schemaDriftRejections === 5, "schema_drift_matrix");
  requireCondition(consoleErrors.length === 0, "console_errors");
  process.stdout.write(`${JSON.stringify({
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
