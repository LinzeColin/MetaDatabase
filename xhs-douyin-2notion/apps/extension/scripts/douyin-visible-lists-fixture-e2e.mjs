import { chromium } from "@playwright/test";

import {
  extractDouyinVisibleBatch,
  validateDouyinVisibleBatch,
} from "../src/douyin-visible-lists.js";


class FixtureFailure extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function requireCondition(condition, code) {
  if (!condition) throw new FixtureFailure(code);
}

function cards(prefix, count = 20) {
  return Array.from({ length: count }, (_, index) => `
    <article data-e2e="feed-item" data-x2n-title="Fixture ${index}">
      <a href="/video/${prefix}-${String(index).padStart(2, "0")}">card</a>
    </article>
  `).join("");
}

function documentFor(mode, options = {}) {
  const label = mode === "favorites" ? "收藏" : "喜欢";
  const listSurface = mode === "favorites" ? "user-favorite-list" : "user-like-list";
  const selected = options.cosmeticOnly
    ? `<span class="active">${label}</span>`
    : `<button role="tab" aria-selected="true">${label}</button>`;
  return `<!doctype html><html><body>${selected}<main data-e2e="${options.listSurface ?? listSurface}">${cards(`fixture-${mode}`, options.count ?? 20)}</main></body></html>`;
}

let browser;
let currentCase = "bootstrap";
try {
  browser = await chromium.launch({ channel: "chromium", headless: true });
  const page = await browser.newPage();
  let currentDocument = "";
  let blockedPlatformNetworkRequests = 0;
  let fixtureDocumentsFulfilled = 0;
  let scrollCalls = 0;
  await page.route("**/*", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      request.isNavigationRequest()
      && request.resourceType() === "document"
      && url.origin === "https://www.douyin.com"
    ) {
      fixtureDocumentsFulfilled += 1;
      return route.fulfill({ body: currentDocument, contentType: "text/html; charset=utf-8", status: 200 });
    }
    blockedPlatformNetworkRequests += 1;
    return route.abort("blockedbyclient");
  });

  for (const mode of ["favorites", "likes"]) {
    currentCase = mode;
    currentDocument = documentFor(mode);
    await page.goto("https://www.douyin.com/user/self", { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      globalThis.__x2nScrollCalls = 0;
      globalThis.scrollTo = () => { globalThis.__x2nScrollCalls += 1; };
    });
    const facts = validateDouyinVisibleBatch(await page.evaluate(extractDouyinVisibleBatch, {
      maxItems: 20,
      mode,
      ownerGesture: true,
      scopeMode: "owner_mvp_20",
    }));
    requireCondition(facts.status === "ready", `${mode}_ready`);
    requireCondition(facts.batch.completion_signal === "bounded_limit_reached", `${mode}_bounded`);
    requireCondition(facts.items.length === 20, `${mode}_count`);
    requireCondition(new Set(facts.items.map((item) => item.content_id)).size === 20, `${mode}_unique`);
    requireCondition(!/\b(?:href|html|media|raw_dom|src)\b/iu.test(JSON.stringify(facts)), `${mode}_raw_surface`);
    scrollCalls += await page.evaluate(() => globalThis.__x2nScrollCalls);
  }

  currentCase = "cosmetic_selection";
  currentDocument = documentFor("favorites", { cosmeticOnly: true });
  await page.goto("https://www.douyin.com/user/self", { waitUntil: "domcontentloaded" });
  const cosmetic = validateDouyinVisibleBatch(await page.evaluate(extractDouyinVisibleBatch, {
    maxItems: 20,
    mode: "favorites",
    ownerGesture: true,
    scopeMode: "owner_mvp_20",
  }));
  requireCondition(cosmetic.status === "platform_changed", "cosmetic_selection_rejected");
  requireCondition(cosmetic.code === "X2N_PLATFORM_CHANGED", "cosmetic_selection_code");

  currentCase = "wrong_list_surface";
  currentDocument = documentFor("favorites", { listSurface: "user-post-list" });
  await page.goto("https://www.douyin.com/user/self", { waitUntil: "domcontentloaded" });
  const wrongSurface = validateDouyinVisibleBatch(await page.evaluate(extractDouyinVisibleBatch, {
    maxItems: 20,
    mode: "favorites",
    ownerGesture: true,
    scopeMode: "owner_mvp_20",
  }));
  requireCondition(wrongSurface.status === "platform_changed", "wrong_list_surface_rejected");
  requireCondition(wrongSurface.code === "X2N_PLATFORM_CHANGED", "wrong_list_surface_code");

  currentCase = "duplicate_card";
  currentDocument = documentFor("likes").replace("fixture-likes-01", "fixture-likes-00");
  await page.goto("https://www.douyin.com/user/self", { waitUntil: "domcontentloaded" });
  const duplicate = validateDouyinVisibleBatch(await page.evaluate(extractDouyinVisibleBatch, {
    maxItems: 20,
    mode: "likes",
    ownerGesture: true,
    scopeMode: "owner_mvp_20",
  }));
  requireCondition(duplicate.status === "partial", "duplicate_rejected");
  requireCondition(duplicate.items.length < 20, "duplicate_no_silent_drop");

  requireCondition(blockedPlatformNetworkRequests === 0, "unexpected_platform_request");
  requireCondition(fixtureDocumentsFulfilled === 5, "fixture_document_count");
  requireCondition(scrollCalls === 0, "automatic_scroll");
  process.stdout.write(`${JSON.stringify({
    automatic_scrolls: 0,
    fixture_documents_fulfilled: fixtureDocumentsFulfilled,
    owner_mvp: "NOT_RUN",
    platform_calls: 0,
    semantic_surface_cases: 5,
    status: "PASS",
  })}\n`);
} catch (error) {
  const code = error instanceof FixtureFailure ? error.code : `unexpected_${currentCase}`;
  process.stderr.write(`${JSON.stringify({ code, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
