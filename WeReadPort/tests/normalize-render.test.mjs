import test from "node:test";
import assert from "node:assert/strict";
import { EXPORT_PROFILES, USER_REGION_END, USER_REGION_START } from "../src/core/constants.js";
import {
  assembleCanonicalBook,
  normalizeBookInfo,
  normalizeBookmarkList,
  normalizeChapterInfo,
  normalizeNotebookPage,
  normalizeProgress,
  normalizeReadingStatistics,
  normalizeReviewPage,
} from "../src/core/normalize.js";
import { renderBookMarkdown } from "../src/core/render.js";
import { fixture } from "./helpers.mjs";

async function canonicalBook() {
  const overview = normalizeNotebookPage(await fixture("notebooks-page-1.json")).summaries[0];
  return assembleCanonicalBook({
    overview,
    info: normalizeBookInfo(await fixture("info.json"), overview),
    progress: normalizeProgress(await fixture("progress.json"), overview),
    bookmarks: normalizeBookmarkList(await fixture("bookmarks.json"), overview.bookId),
    reviews: [
      ...normalizeReviewPage(await fixture("reviews-page-1.json"), overview.bookId).reviews,
      ...normalizeReviewPage(await fixture("reviews-page-2.json"), overview.bookId).reviews,
    ],
    extraChapters: normalizeChapterInfo(await fixture("chapters.json")),
  });
}

test("normalization distinguishes highlights, thoughts, book reviews and bookmark count", async () => {
  const book = await canonicalBook();
  assert.equal(book.metadata.title, "复杂系统入门");
  assert.equal(book.counts.highlights, 1);
  assert.equal(book.counts.thoughtsAndReviews, 2);
  assert.equal(book.counts.officialBookmarkCount, 1);
  assert.equal(book.progress.readingTimeSeconds, 3661);
  assert.equal(book.metadata.rating, 8.6);
  assert.equal(book.thoughts[0].kind, "highlight-thought");
  assert.equal(book.thoughts[1].kind, "book-review");
  assert.ok(book.warnings.some(value => value.includes("书签仅计数")));
});

test("four profiles preserve core content and expose target-specific structure", async () => {
  const book = await canonicalBook();
  const portable = renderBookMarkdown(book, { profile: EXPORT_PROFILES.PORTABLE });
  const gfm = renderBookMarkdown(book, { profile: EXPORT_PROFILES.GFM });
  const obsidian = renderBookMarkdown(book, { profile: EXPORT_PROFILES.OBSIDIAN });
  const notion = renderBookMarkdown(book, { profile: EXPORT_PROFILES.NOTION });
  for (const markdown of [portable, gfm, obsidian, notion]) {
    assert.match(markdown, /复杂系统入门/);
    assert.match(markdown, /系统的行为来自关系/);
    assert.match(markdown, /这说明局部优化可能损害整体/);
    assert.match(markdown, new RegExp(USER_REGION_START.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(markdown, new RegExp(USER_REGION_END.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(gfm, /\| 字段 \| 内容 \|/);
  assert.match(obsidian, /> \[!quote\]/);
  assert.ok(portable.startsWith("---\n"));
  assert.ok(!notion.startsWith("---\n"));
});


test("official reading-statistics fields normalize without alias guesswork", () => {
  const statistics = normalizeReadingStatistics({
    mode: "overall",
    totalReadTime: 7205,
    readDays: 9,
    readStat: [{ stat: "读完", counts: "3本" }],
  });
  assert.deepEqual(statistics, {
    mode: "overall",
    totalReadingTimeSeconds: 7205,
    totalReadingDays: 9,
    totalFinishedBooks: 3,
  });
  assert.deepEqual(normalizeReadingStatistics({ readTime: 120 }, { mode: "weekly" }), {
    mode: "weekly",
    totalReadingTimeSeconds: 120,
    totalReadingDays: undefined,
    totalFinishedBooks: undefined,
  });
});
