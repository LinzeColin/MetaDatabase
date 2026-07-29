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

function observedProfileHtml({ label, duplicateSelectedLabel = null }) {
  const duplicateList = duplicateSelectedLabel === null
    ? '<div class="reds-tabs-list tertiary"><div class="unrelated-control">other</div></div>'
    : `<div class="reds-tabs-list tertiary"><div class="reds-tab-item sub-tab-list active">${duplicateSelectedLabel}</div></div>`;
  return `<!doctype html><html><body>
    <div id="userPageContainer" class="user-page">
      <div class="reds-tabs-list tertiary">
        <div class="reds-tab-item sub-tab-list">笔记</div>
        <div class="reds-tab-item sub-tab-list active">${label}</div>
      </div>
      ${duplicateList}
      <div id="userPostedFeeds"><article data-x2n-card data-x2n-note-type="video">
        <a href="/explore/synth-observed-profile-item">synthetic item</a>
      </article></div>
    </div>
  </body></html>`;
}

function observedProfileTabbedHtml({ label, visiblePanelIndexes }) {
  const labels = ["笔记", "收藏", "点赞"];
  const activeIndex = labels.indexOf(label);
  if (activeIndex < 0) throw new Error("unsupported tabbed profile relation");
  const cards = (count, prefix) => Array.from({ length: count }, (_, index) => (
    `<article data-x2n-card data-x2n-note-type="video"><a href="/explore/${prefix}-${index + 1}">synthetic item</a></article>`
  )).join("");
  const visible = new Set(visiblePanelIndexes);
  const panels = labels.map((relation, index) => {
    const style = visible.has(index)
      ? "position:relative;width:480px;min-height:300px"
      : "position:absolute;left:-10000px;top:0;width:480px;min-height:1px";
    const content = index === 0
      ? `<div id="userPostedFeeds">${cards(1, "static-posts")}</div>`
      : cards(index === activeIndex ? 25 : 0, `active-${index}`);
    return `<div class="tab-content-item" style="${style}">${content}</div>`;
  }).join("");
  return `<!doctype html><html><body>
    <div id="userPageContainer" class="user-page">
      <div class="reds-tabs-list tertiary">
        ${labels.map((relation) => `<div class="reds-tab-item sub-tab-list${relation === label ? " active" : ""}">${relation}</div>`).join("")}
      </div>
      <div class="feeds-tab-container"><div class="transform-container" style="position:relative;display:flex">${panels}</div></div>
    </div>
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
  {
    id: "favorites_multiple_tertiary_lists_unique_selected_relation_accepted",
    html: observedProfileHtml({ label: "收藏" }),
    expectedItems: 1,
    expectedStatus: "ready",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  },
  {
    id: "likes_current_label_alias_multiple_tertiary_lists_accepted",
    html: observedProfileHtml({ label: "点赞" }),
    expectedItems: 1,
    expectedStatus: "ready",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
  {
    id: "favorites_ambiguous_multiple_selected_relations_rejected",
    html: observedProfileHtml({ label: "收藏", duplicateSelectedLabel: "收藏" }),
    expectedItems: 0,
    expectedStatus: "platform_changed",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  },
  {
    id: "likes_nonmatching_secondary_relation_ignored",
    html: observedProfileHtml({ label: "点赞", duplicateSelectedLabel: "收藏" }),
    expectedItems: 1,
    expectedStatus: "ready",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
  {
    id: "likes_ambiguous_multiple_selected_relations_rejected",
    html: observedProfileHtml({ label: "点赞", duplicateSelectedLabel: "点赞" }),
    expectedItems: 0,
    expectedStatus: "platform_changed",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
  {
    id: "favorites_active_transform_panel_selected_over_static_posts",
    html: observedProfileTabbedHtml({ label: "收藏", visiblePanelIndexes: [1] }),
    expectedItems: 20,
    expectedStatus: "ready",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
  },
  {
    id: "likes_active_transform_panel_selected_over_static_posts",
    html: observedProfileTabbedHtml({ label: "点赞", visiblePanelIndexes: [2] }),
    expectedItems: 20,
    expectedStatus: "ready",
    extract: extractXhsLikesVisibleBatch,
    validate: validateXhsLikesBatch,
  },
  {
    id: "favorites_ambiguous_transform_panels_rejected",
    html: observedProfileTabbedHtml({ label: "收藏", visiblePanelIndexes: [1, 2] }),
    expectedItems: 0,
    expectedStatus: "platform_changed",
    extract: extractXhsFavoritesVisibleBatch,
    validate: validateXhsFavoritesBatch,
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
    currentHtml = testCase.html ?? profileHtml(testCase);
    await page.goto(`https://www.xiaohongshu.com/user/profile/${testCase.id}`, { waitUntil: "domcontentloaded" });
    const result = testCase.validate(await page.evaluate(
      testCase.extract,
      { maxItems: 20, ownerGesture: true, scopeMode: "full_scan" },
    ));
    requireCondition(result.status === testCase.expectedStatus, "profile_surface_status");
    requireCondition(result.batch.automatic_scroll === false, "automatic_scroll");
    requireCondition(result.batch.explicit_owner_action === true, "owner_action");
    const expectedItems = testCase.expectedItems ?? (testCase.semantic ? 1 : 0);
    requireCondition(result.items.length === expectedItems, "profile_surface_item_count");
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
