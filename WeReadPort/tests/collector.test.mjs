import test from "node:test";
import assert from "node:assert/strict";
import { collectNotebookSummaries, collectSnapshot } from "../src/core/collector.js";
import { EXPORT_PROFILES } from "../src/core/constants.js";
import { fixture } from "./helpers.mjs";

test("collector paginates notebooks and reviews without loops", async () => {
  const page1 = await fixture("notebooks-page-1.json");
  const page2 = await fixture("notebooks-page-2.json");
  const bookmarks = await fixture("bookmarks.json");
  const reviews1 = await fixture("reviews-page-1.json");
  const reviews2 = await fixture("reviews-page-2.json");
  const info = await fixture("info.json");
  const progress = await fixture("progress.json");
  const chapters = await fixture("chapters.json");
  const calls = [];
  const call = async ({ apiName, params }) => {
    calls.push({ apiName, params });
    if (apiName === "/user/notebooks") return params.lastSort === undefined ? page1 : page2;
    if (apiName === "/book/bookmarklist") return bookmarks;
    if (apiName === "/review/list/mine") return params.synckey === 0 ? reviews1 : reviews2;
    if (apiName === "/book/info") return info;
    if (apiName === "/book/getprogress") return progress;
    if (apiName === "/book/chapterinfo") return chapters;
    if (apiName === "/readdata/detail") return { mode: "overall", totalReadTime: 9000, readDays: 3, readStat: [{ stat: "读完", counts: "1本" }] };
    throw new Error(`unexpected ${apiName}`);
  };
  const summaries = await collectNotebookSummaries({ key: "unused-by-mock", call });
  assert.equal(summaries.length, 2);
  assert.ok(calls.some(item => item.apiName === "/user/notebooks" && item.params.lastSort === 200));
  const snapshot = await collectSnapshot({ key: "unused-by-mock", summaries: [summaries.find(item => item.bookId === "book-001")], exportProfile: EXPORT_PROFILES.PORTABLE, call, includeReadingStatistics: true });
  assert.equal(snapshot.books.length, 1);
  assert.equal(snapshot.books[0].thoughts.length, 2);
  assert.equal(snapshot.readingStatistics.totalReadingTimeSeconds, 9000);
  assert.equal(snapshot.readingStatistics.totalReadingDays, 3);
  assert.equal(snapshot.readingStatistics.totalFinishedBooks, 1);
});

test("all-book failure cannot become an empty success", async () => {
  const summaries = [{ bookId: "x", title: "x", author: "", highlightCount: 1, reviewCount: 0, bookmarkCount: 0, totalNoteCount: 1 }];
  await assert.rejects(() => collectSnapshot({ key: "unused", summaries, exportProfile: EXPORT_PROFILES.PORTABLE, call: async () => { throw new Error("network"); } }), error => error.code === "NO_EXPORTABLE_DATA");
});
