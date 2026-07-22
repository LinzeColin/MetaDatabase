import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import {
  buildTaobaoCapturePayload,
  extractTaobaoCurrentPage,
  validateTaobaoPageFacts,
} from "../src/taobao-current-page.js";
import { recognizePage } from "../src/page-support.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/taobao_current_page");
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
      const platformRequest = requestUrl.hostname.toLowerCase() === "item.taobao.com";
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
    const facts = validateTaobaoPageFacts(await page.evaluate(extractTaobaoCurrentPage));
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
      requireCondition(canonical.hostname === "item.taobao.com", "canonical_host");
      requireCondition(canonical.pathname === "/item.htm", "canonical_path");
      const payload = buildTaobaoCapturePayload(facts);
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
  let scopeRetentionDisabledCasesVerified = 0;
  for (const policyCase of manifest.policy_cases) {
    currentCase = policyCase.id;
    const result = recognizePage(policyCase.url);
    requireCondition(exactObject(result, policyCase.expected), "policy_state_diff");
    if (result.reason === "taobao_scope_retention_unknown_disabled") {
      scopeRetentionDisabledCasesVerified += 1;
    }
    policyCasesVerified += 1;
  }

  let undocumentedSignatureRejections = 0;
  for (const signatureCase of manifest.undocumented_signature_cases) {
    currentCase = signatureCase.id;
    const result = recognizePage(signatureCase.url);
    requireCondition(
      exactObject(result, {
        executable: false,
        platform: "taobao",
        reason: "taobao_undocumented_signature_input_rejected",
        supported: true,
      }),
      "undocumented_signature_not_rejected",
    );
    undocumentedSignatureRejections += 1;
  }

  let schemaDriftRejections = 0;
  const validFacts = {
    page_context: {
      content_id: "9900000000000999201",
      content_type: "text",
      title: "Synthetic validator title",
    },
    page_url: "https://item.taobao.com/item.htm",
    platform: "taobao",
    provenance: {
      canonical_url: { source: "stable_num_iid_and_official_item_route", status: "derived" },
      content_id: { source: "location_semantic_id_and_item_surface", status: "observed_verified" },
      content_type: { source: "item_text_marker", status: "observed" },
      title: { source: "item_heading", status: "observed" },
    },
    schema_version: "1.0",
    status: "ready",
  };
  const invalidFacts = [
    { ...validFacts, preview_url: "synthetic-value" },
    { ...validFacts, undocumented_input: "synthetic-value" },
    { ...validFacts, media_url: "synthetic-value" },
    {
      ...validFacts,
      page_context: { ...validFacts.page_context, content_id: "1234567890123" },
      page_url: "https://item.taobao.com/item.htm?id=1234567890123",
    },
    { ...validFacts, page_context: { ...validFacts.page_context, title: "https://media.invalid/value" } },
    { ...validFacts, page_url: `${validFacts.page_url}?tracking=synthetic` },
  ];
  for (const invalid of invalidFacts) {
    try {
      validateTaobaoPageFacts(invalid);
    } catch {
      schemaDriftRejections += 1;
    }
  }
  try {
    buildTaobaoCapturePayload(validateTaobaoPageFacts({
      code: "X2N_PLATFORM_CHANGED",
      platform: "taobao",
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
  requireCondition(scopeRetentionDisabledCasesVerified === 2, "scope_retention_matrix");
  requireCondition(
    undocumentedSignatureRejections === manifest.undocumented_signature_cases.length,
    "undocumented_signature_matrix",
  );
  requireCondition(schemaDriftRejections === 7, "schema_drift_matrix");
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
    scope_retention_disabled_cases_verified: scopeRetentionDisabledCasesVerified,
    stable_ids_verified: stableIdsVerified,
    status: "PASS",
    undocumented_signature_rejections: undocumentedSignatureRejections,
  })}\n`);
} catch (error) {
  const code = error instanceof FixtureFailure ? error.code : `unexpected_${currentCase}`;
  process.stderr.write(`${JSON.stringify({ code, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
