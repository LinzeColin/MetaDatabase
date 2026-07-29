import { chromium } from "@playwright/test";

import {
  extractXhsFavoritesVisibleBatch,
  validateXhsFavoritesBatch,
} from "../src/xhs-favorites.js";
import {
  extractXhsLikesVisibleBatch,
  validateXhsLikesBatch,
} from "../src/xhs-likes.js";


function requireCondition(condition, code) {
  if (!condition) throw new Error(code);
}

function profileHtml({ label, semantic }) {
  const control = semantic
    ? `<button aria-selected="true">${label}</button>`
    : `<div class="active">${label}</div>`;
  return `<!doctype html><html><body>
    <nav>${control}</nav>
    <main><article data-x2n-card data-x2n-note-type="video">
      <a href="/explore/synth-mvp-surface-item">synthetic item</a>
    </article></main>
  </body></html>`;
}

const cases = [
  {
    id: "favorites_profile_counter_rejected",
    label: "收藏",
    semantic: false,
    expectedStatus: "platform_changed",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  },
  {
    id: "favorites_selected_control_accepted",
    label: "收藏",
    semantic: true,
    expectedStatus: "ready",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  },
  {
    id: "likes_profile_counter_rejected",
    label: "赞过",
    semantic: false,
    expectedStatus: "platform_changed",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
  {
    id: "likes_selected_control_accepted",
    label: "赞过",
    semantic: true,
    expectedStatus: "ready",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
];

let browser;
let currentCase = "bootstrap";
try {
  browser = await chromium.launch({ channel: "chromium", headless: true });
  const page = await browser.newPage();
  const unexpectedRequests = [];
  let currentHtml = "";
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() === "document") {
      return route.fulfill({ body: currentHtml, contentType: "text/html; charset=utf-8", status: 200 });
    }
    unexpectedRequests.push("blocked_non_document_request");
    return route.abort("blockedbyclient");
  });

  for (const testCase of cases) {
    currentCase = testCase.id;
    currentHtml = profileHtml(testCase);
    await page.goto(`https://www.xiaohongshu.com/user/profile/${testCase.id}`, { waitUntil: "domcontentloaded" });
    const result = testCase.validate(await page.evaluate(
      testCase.extract,
      { maxItems: 20, ownerGesture: true, scopeMode: "full_scan" },
    ));
    requireCondition(result.status === testCase.expectedStatus, "profile_surface_status");
    requireCondition(result.batch.automatic_scroll === false, "automatic_scroll");
    requireCondition(result.batch.explicit_owner_action === true, "owner_action");
    requireCondition(
      (testCase.semantic && result.items.length === 1) || (!testCase.semantic && result.items.length === 0),
      "profile_surface_item_count",
    );
  }
  requireCondition(unexpectedRequests.length === 0, "unexpected_network_requests");
  process.stdout.write(`${JSON.stringify({
    automatic_scrolls: 0,
    fixture_cases: cases.length,
    network_calls: 0,
    platform_calls: 0,
    status: "PASS",
  })}\n`);
} catch {
  process.stderr.write(`${JSON.stringify({ code: `xhs_mvp_surface_${currentCase}`, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
}
