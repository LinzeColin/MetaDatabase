import test from "node:test";
import assert from "node:assert/strict";
import { syncWeReadDataset, WIDE_SCOPE_APIS } from "../../service/platform/weread.mjs";
import { testPlatform } from "./helpers.mjs";

const KEY = `wrk-${"W".repeat(32)}`;
function gatewayMock(calls) {
  return async (_url, init) => {
    const body = JSON.parse(init.body);
    const api = body.api_name;
    calls.push(api);
    const ids = Array.from({ length: 8 }, (_, index) => `book-${index + 1}`);
    let payload = { errcode: 0 };
    if (api === "/_list") payload.apis = [...WIDE_SCOPE_APIS];
    else if (api === "/shelf/sync") payload.books = ids.map(bookId => ({ bookId }));
    else if (api === "/user/notebooks") payload = { errcode: 0, books: ids.map((bookId, index) => ({ bookId, sort: 1000 - index, book: { bookId, title: `书籍 ${index + 1}`, author: "作者", category: "研究" } })), totalNoteCount: 16, hasMore: false };
    else if (api === "/book/bookmarklist") payload = { errcode: 0, updated: [{ bookmarkId: `bm-${body.bookId}`, bookId: body.bookId, markText: `划线 ${body.bookId}`, createTime: 100 }], chapters: [{ chapterUid: 1, title: "第一章" }] };
    else if (api === "/review/list/mine") payload = { errcode: 0, reviews: [{ review: { reviewId: `rv-${body.bookid}`, content: `想法 ${body.bookid}`, createTime: 101 } }], totalCount: 1, hasMore: false, synckey: 1 };
    else if (api === "/book/info") payload = { errcode: 0, bookId: body.bookId, title: `书籍 ${body.bookId}`, author: "作者", category: "研究" };
    else if (api === "/book/getprogress") payload = { errcode: 0, bookId: body.bookId, progress: 42 };
    else if (api === "/book/chapterinfo") payload = { errcode: 0, chapters: [{ chapterUid: 1, title: "第一章" }] };
    else if (api === "/book/bestbookmarks") payload = { errcode: 0, items: [] };
    else if (api === "/readdata/detail") payload = { errcode: 0, mode: body.mode, readTime: 120 };
    else if (api === "/book/recommend") payload = body.maxIdx ? { errcode: 0, books: [] } : { errcode: 0, books: [{ bookId: "recommend-1", title: "推荐书", author: "推荐作者", searchIdx: 1, reason: "与你的阅读主题相关" }] };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  };
}

test("微信读书按能力发现读取超过 Top 5 的书架、全量笔记、进度、统计与推荐", async () => {
  const calls = [];
  const dataset = await syncWeReadDataset(KEY, { fetchImpl: gatewayMock(calls), maxBooks: 100, recommendationPages: 2 });
  assert.equal(dataset.summary.notebookBooks, 8);
  assert.equal(dataset.summary.detailedBooks, 8);
  assert.equal(dataset.summary.totalNoteCount, 16);
  assert.equal(dataset.readingStats.weekly.readTime, 120);
  assert.equal(dataset.recommendations.length, 1);
  for (const api of ["/_list", "/shelf/sync", "/user/notebooks", "/book/bookmarklist", "/review/list/mine", "/book/info", "/book/getprogress", "/book/chapterinfo", "/readdata/detail", "/book/recommend"]) assert.ok(calls.includes(api), api);
  assert.ok(calls.filter(api => api === "/book/info").length > 5, "不得回退为 Top 5");
});

test("广范围微信读书同步保存到账户并生成官方可解释推荐", async t => {
  const calls = [];
  const platform = testPlatform({ fetchImpl: gatewayMock(calls) });
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY, displayName: "微信读书用户" }, {}, { verify: false });
  const result = await platform.service.syncWeRead(user.account.id, { recommendationPages: 2 });
  assert.equal(result.summary.detailedBooks, 8);
  assert.equal(result.summary.importedDocuments, 16);
  assert.equal(platform.service.listNotes(user.account.id, { limit: 100 }).length, 16);
  platform.service.updateConsent(user.account.id, { behaviorAnalytics: false, recommendationPersonalization: true });
  assert.ok(platform.service.analytics(user.account.id).recommendations.some(item => item.source === "weread-official"));
});
