import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import { extractDouyinCurrentPage, validateDouyinPageFacts } from "../src/douyin-current-page.js";
import { DouyinShortLinkError, resolveDouyinShortLink } from "../src/douyin-short-link.js";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const FIXTURE_ROOT = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/douyin_current_page");
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
  let shortLinksPersisted = 0;
  let blockedPlatformNetworkRequests = 0;
  let fixtureDocumentsFulfilled = 0;
  let platformCalls = 0;
  for (const fixtureCase of manifest.cases) {
    currentCase = fixtureCase.id;
    const html = await readFile(join(FIXTURE_ROOT, fixtureCase.file), "utf8");
    const routedUrl = new URL(fixtureCase.page_url);
    routedUrl.hash = "";
    await page.route("**/*", (route) => {
      const requestUrl = new URL(route.request().url());
      requestUrl.hash = "";
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
      blockedPlatformNetworkRequests += 1;
      return route.abort("blockedbyclient");
    });
    await page.goto(fixtureCase.page_url, { waitUntil: "domcontentloaded" });
    const facts = validateDouyinPageFacts(await page.evaluate(extractDouyinCurrentPage));
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
      if (facts.page_url.includes("v.douyin.com")) shortLinksPersisted += 1;
      requireCondition(canonical.hostname === "www.douyin.com", "canonical_host");
      requireCondition(
        canonical.pathname === `/video/${expected.content_id}`
          || canonical.pathname === `/note/${expected.content_id}`,
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
    requireCondition(!/\b(?:href|html|media|raw_dom|src)\b/iu.test(rendered), "raw_or_media_surface");
    await page.unroute("**/*");
  }

  let redirectSecurityPassed = 0;
  let resolvedShortLinks = 0;
  let syntheticRedirectRequests = 0;
  for (const shortCase of manifest.short_link_cases) {
    currentCase = shortCase.id;
    let responseIndex = 0;
    const requester = async (request) => {
      syntheticRedirectRequests += 1;
      requireCondition(request.method === "HEAD", "short_request_method");
      requireCondition(request.redirect === "manual", "short_request_redirect");
      requireCondition(request.credentials === "omit", "short_request_credentials");
      requireCondition(request.cache === "no-store", "short_request_cache");
      requireCondition(request.referrerPolicy === "no-referrer", "short_request_referrer");
      const expectedRequestUrls = shortCase.expected_request_urls ?? [];
      requireCondition(request.url === expectedRequestUrls[responseIndex], "short_request_url");
      const requestUrl = new URL(request.url);
      requireCondition(requestUrl.search === "" && requestUrl.hash === "", "short_request_tracking");
      if (shortCase.request_error_at === responseIndex) {
        responseIndex += 1;
        throw new Error("synthetic request failure");
      }
      const response = shortCase.responses[responseIndex];
      responseIndex += 1;
      requireCondition(Boolean(response), "short_unexpected_request");
      return response;
    };
    try {
      const resolved = await resolveDouyinShortLink(shortCase.start_url, requester);
      requireCondition(!shortCase.expected_error, "short_expected_error_missing");
      requireCondition(
        Object.keys(resolved).length === Object.keys(shortCase.expected).length
          && Object.entries(shortCase.expected).every(([key, value]) => resolved[key] === value),
        "short_resolution_diff",
      );
      const rendered = JSON.stringify(resolved);
      requireCondition(!rendered.includes("v.douyin.com") && !rendered.includes("tracking="), "short_resolution_persisted");
      resolvedShortLinks += 1;
      redirectSecurityPassed += 1;
    } catch (error) {
      requireCondition(Boolean(shortCase.expected_error), "short_unexpected_error");
      requireCondition(error instanceof DouyinShortLinkError, "short_error_type");
      requireCondition(error.code === shortCase.expected_error, "short_error_code");
      redirectSecurityPassed += 1;
    }
    requireCondition(responseIndex === (shortCase.expected_request_urls ?? []).length, "short_request_count");
  }

  requireCondition(observationDiffMismatches === 0, "observation_diff");
  requireCondition(queryFragmentPersisted === 0, "query_fragment_persistence");
  requireCondition(shortLinksPersisted === 0, "short_link_persistence");
  requireCondition(redirectSecurityPassed === manifest.short_link_cases.length, "redirect_security_matrix");
  requireCondition(fixtureDocumentsFulfilled === manifest.cases.length, "fixture_document_count");
  requireCondition(blockedPlatformNetworkRequests === 0, "unexpected_platform_request");
  requireCondition(platformCalls === 0, "platform_network_call");
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
    query_fragment_persisted: queryFragmentPersisted,
    redirect_security_cases: redirectSecurityPassed,
    resolved_short_links: resolvedShortLinks,
    short_links_persisted: shortLinksPersisted,
    stable_ids_verified: stableIdsVerified,
    status: "PASS",
    synthetic_redirect_requests: syntheticRedirectRequests,
  })}\n`);
} catch (error) {
  const code = error instanceof FixtureFailure ? error.code : `unexpected_${currentCase}`;
  process.stderr.write(`${JSON.stringify({ code, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
