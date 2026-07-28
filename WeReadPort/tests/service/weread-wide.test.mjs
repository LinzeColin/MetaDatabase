import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { normalizeWeReadDocuments, recommendationRows, syncWeReadDataset, WIDE_SCOPE_APIS } from "../../service/platform/weread.mjs";
import { PlatformStore } from "../../service/platform/store.mjs";
import { testPlatform } from "./helpers.mjs";

const KEY = `wrk-${"W".repeat(32)}`;
const EVENT_BASE = 1_700_000_000;

test("旧账户数据库启动时为笔记补齐事件时间列且不丢数据", async t => {
  const directory = await mkdtemp(path.join(tmpdir(), "weread-event-time-"));
  const databasePath = path.join(directory, "platform.sqlite3");
  const legacy = new DatabaseSync(databasePath);
  legacy.exec(`CREATE TABLE notes (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, source TEXT NOT NULL, external_id TEXT NOT NULL,
    title TEXT NOT NULL, object_key TEXT NOT NULL, content_hash TEXT NOT NULL, word_count INTEGER NOT NULL DEFAULT 0,
    category TEXT, version INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, deleted_at INTEGER,
    UNIQUE(account_id, source, external_id)
  ) STRICT;`);
  legacy.prepare("INSERT INTO notes(id,account_id,source,external_id,title,object_key,content_hash,word_count,category,version,created_at,updated_at,deleted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)")
    .run("note_legacy", "acct_legacy", "weread", "highlight:legacy", "旧书摘", "legacy.enc", "hash", 2, "微信读书", 1, EVENT_BASE, EVENT_BASE + 50, null);
  legacy.close();
  const store = new PlatformStore(databasePath, { clock: () => (EVENT_BASE + 100) * 1000 });
  t.after(async () => { store.close(); await rm(directory, { recursive: true, force: true }); });
  assert.equal(store.getNote("acct_legacy", "note_legacy").eventAt, EVENT_BASE);
  assert.ok(store.db.prepare("PRAGMA table_info(notes)").all().some(column => column.name === "event_at"));
});

function gatewayMock(calls, { changedBook = () => "" } = {}) {
  return async (_url, init) => {
    const body = JSON.parse(init.body);
    const api = body.api_name;
    calls.push(api);
    const ids = Array.from({ length: 8 }, (_, index) => `book-${index + 1}`);
    let payload = { errcode: 0 };
    if (api === "/_list") payload.apis = [...WIDE_SCOPE_APIS];
    else if (api === "/shelf/sync") payload.books = ids.map(bookId => ({ bookId }));
    else if (api === "/user/notebooks") payload = { errcode: 0, books: ids.map((bookId, index) => ({ bookId, sort: EVENT_BASE + 1_000 - index + (changedBook() === bookId ? 3_600 : 0), noteCount: 1, reviewCount: 1, bookmarkCount: 0, book: { bookId, title: `书籍 ${index + 1}`, author: "作者", category: "研究" } })), totalNoteCount: 16, hasMore: false };
    else if (api === "/book/bookmarklist") { const index = Number(String(body.bookId).replace(/\D/g, "")); const updateTime = EVENT_BASE + 10 + index; payload = { errcode: 0, updated: [{ bookmarkId: `bm-${body.bookId}`, bookId: body.bookId, markText: `划线 ${body.bookId}`, createTime: EVENT_BASE + index, updateTime: index === 1 ? updateTime * 1000 : updateTime }], chapters: [{ chapterUid: 1, title: "第一章" }] }; }
    else if (api === "/review/list/mine") { const index = Number(String(body.bookid).replace(/\D/g, "")); payload = { errcode: 0, reviews: [{ review: { reviewId: `rv-${body.bookid}`, content: `想法 ${body.bookid}`, createTime: EVENT_BASE + 100 + index } }], totalCount: 1, hasMore: false, synckey: 1 }; }
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

test("微信读书将书摘和想法显示为可区分的具体笔记标题", async () => {
  const dataset = await syncWeReadDataset(KEY, { fetchImpl: gatewayMock([]), maxBooks: 100, recommendationPages: 1 });
  const documents = normalizeWeReadDocuments(dataset);
  const highlight = documents.find(item => item.externalId === "highlight:bm-book-1");
  const review = documents.find(item => item.externalId === "review:rv-book-1");
  assert.match(highlight.title, /^书摘｜《书籍 book-1》 · 划线 book-1$/u);
  assert.match(review.title, /^想法｜《书籍 book-1》 · 想法 book-1$/u);
  assert.notEqual(highlight.title, review.title);
});

test("广范围微信读书同步保存到账户并生成官方可解释推荐", async t => {
  const calls = [];
  const platform = testPlatform({ fetchImpl: gatewayMock(calls) });
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY, displayName: "微信读书用户" }, {}, { verify: false });
  const result = await platform.service.syncWeRead(user.account.id, { recommendationPages: 2 });
  assert.equal(result.summary.detailedBooks, 8);
  assert.equal(result.summary.importedDocuments, 16);
  assert.equal(result.summary.coverage.verified, true);
  assert.equal(result.summary.coverage.unresolvedDocuments, 0);
  assert.deepEqual(platform.service.publicAccount(user.account.id).weread.summary.coverage, result.summary.coverage);
  assert.equal(platform.service.listNotes(user.account.id, { limit: 100 }).length, 16);
  platform.service.updateConsent(user.account.id, { behaviorAnalytics: false, recommendationPersonalization: true });
  assert.ok(platform.service.analytics(user.account.id).recommendations.some(item => item.source === "weread-official"));
});

test("微信读书保留真实事件时间、按事件倒序且重复同步不重写历史", async t => {
  const calls = [];
  let now = (EVENT_BASE + 86_400) * 1000;
  const platform = testPlatform({ fetchImpl: gatewayMock(calls), clock: () => now });
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY, displayName: "事件时间用户" }, {}, { verify: false });
  const first = await platform.service.syncWeRead(user.account.id, { recommendationPages: 1 });
  const before = platform.service.listNotes(user.account.id, { limit: 100 });
  assert.equal(first.summary.updatedDocuments, 16);
  assert.equal(first.summary.unchangedDocuments, 0);
  assert.equal(before[0].eventAt, EVENT_BASE + 108);
  assert.equal(before.find(note => note.externalId === "highlight:bm-book-1").eventAt, EVENT_BASE + 11);
  assert.ok(before.every((note, index) => index === 0 || Number(before[index - 1].eventAt) >= Number(note.eventAt)));
  const original = new Map(before.map(note => [note.id, { version: note.version, updatedAt: note.updatedAt, eventAt: note.eventAt }]));

  now += 3_600_000;
  const second = await platform.service.syncWeRead(user.account.id, { recommendationPages: 1 });
  const after = platform.service.listNotes(user.account.id, { limit: 100 });
  assert.equal(second.summary.updatedDocuments, 0);
  assert.equal(second.summary.unchangedDocuments, 16);
  for (const note of after) assert.deepEqual({ version: note.version, updatedAt: note.updatedAt, eventAt: note.eventAt }, original.get(note.id));
  const eventDate = new Date((EVENT_BASE + 108) * 1000).toISOString().slice(0, 10);
  assert.ok(platform.service.analytics(user.account.id).readingHeatmap.some(day => day.date === eventDate && day.value > 0));
});

test("微信读书后续同步只读取来源明确变化的书籍，并保留每日完整核对回退", async t => {
  const calls = [];
  let changedBook = "";
  const platform = testPlatform({ fetchImpl: gatewayMock(calls, { changedBook: () => changedBook }) });
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY, displayName: "增量同步用户" }, {}, { verify: false });
  const first = await platform.service.syncWeRead(user.account.id, { recommendationPages: 1 });
  assert.equal(first.summary.syncMode, "full");
  assert.equal(Object.hasOwn(platform.service.publicAccount(user.account.id).weread, "bookState"), false);

  calls.length = 0;
  const second = await platform.service.syncWeRead(user.account.id, { recommendationPages: 1 });
  assert.equal(second.summary.syncMode, "incremental");
  assert.equal(second.summary.detailedBooks, 0);
  assert.equal(second.summary.skippedUnchangedBooks, 8);
  assert.equal(second.summary.unchangedDocuments, 16);
  assert.equal(calls.filter(api => api === "/book/bookmarklist").length, 0);
  assert.equal(calls.filter(api => api === "/review/list/mine").length, 0);
  for (const api of ["/_list", "/shelf/sync", "/user/notebooks"]) assert.ok(calls.includes(api), api);

  changedBook = "book-3";
  calls.length = 0;
  const third = await platform.service.syncWeRead(user.account.id, { recommendationPages: 1 });
  assert.equal(third.summary.syncMode, "incremental");
  assert.equal(third.summary.detailedBooks, 1);
  assert.equal(third.summary.skippedUnchangedBooks, 7);
  assert.equal(calls.filter(api => api === "/book/bookmarklist").length, 1);
  assert.equal(calls.filter(api => api === "/review/list/mine").length, 1);
});

test("微信读书兼容包装字段、分页重叠并为官方推荐生成真实详情链接", async () => {
  const calls = [];
  const ids = ["alias-book-a", "alias-book-b", "alias-book-c"];
  const fetchImpl = async (_url, init) => {
    const body = JSON.parse(init.body);
    calls.push(body.api_name);
    let payload = { errcode: 0 };
    if (body.api_name === "/_list") payload.apis = [...WIDE_SCOPE_APIS];
    else if (body.api_name === "/shelf/sync") payload = { errcode: 0, data: { books: ids.map(bookId => ({ bookId })) } };
    else if (body.api_name === "/user/notebooks") {
      const pageIds = body.lastSort === undefined ? ids.slice(0, 2) : ids.slice(1);
      payload = { errcode: 0, result: { booklist: pageIds.map((bookId, index) => ({ book: { bookId, title: `别名书 ${bookId}`, author: "作者", category: "研究" }, note_count: 1, review_count: 0, sort: 100 - index - (body.lastSort === undefined ? 0 : 1) })), totalNoteCount: 3, has_more: body.lastSort === undefined, last_sort: body.lastSort === undefined ? 99 : undefined } };
    } else if (body.api_name === "/book/bookmarklist") payload = { errcode: 0, data: { bookmarkList: [{ id: `highlight-${body.bookId}`, text: `划线 ${body.bookId}`, createTime: EVENT_BASE + 9, updateTime: EVENT_BASE + 19 }], chapterList: [{ uid: 1, name: "第一章" }] } };
    else if (body.api_name === "/review/list/mine") payload = { errcode: 0, result: { reviewList: [], totalCount: 0, has_more: false } };
    else if (body.api_name === "/book/info") payload = { errcode: 0, data: { book: { bookId: body.bookId, title: `别名书 ${body.bookId}`, author: "作者", category: "研究" } } };
    else if (body.api_name === "/book/getprogress") payload = { errcode: 0, data: { readingProgress: 30 } };
    else if (body.api_name === "/book/chapterinfo") payload = { errcode: 0, result: { chapterList: [{ uid: 1, name: "第一章" }] } };
    else if (body.api_name === "/book/recommend") payload = body.maxIdx ? { errcode: 0, data: { books: [] } } : { errcode: 0, data: { books: [{ bookInfo: { bookId: "abc123-official-book", title: "官方推荐", author: "推荐作者" }, searchIdx: 1, reason: "官方理由" }] } };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  const dataset = await syncWeReadDataset(KEY, { fetchImpl, maxBooks: 100, recommendationPages: 2 });
  const documents = normalizeWeReadDocuments(dataset);
  assert.equal(dataset.summary.notebookBooks, 3);
  assert.equal(documents.length, 3);
  assert.equal(new Set(documents.map(item => item.externalId)).size, 3, "重叠分页不得重复导入");
  assert.equal(calls.filter(api => api === "/user/notebooks").length, 2);
  assert.equal(recommendationRows(dataset)[0].deepLink, "https://weread.qq.com/web/bookDetail/abc123-official-book");
});

test("微信读书分页游标异常时拒绝把不完整结果当成完整同步", async () => {
  const fetchImpl = async (_url, init) => {
    const body = JSON.parse(init.body);
    const payload = body.api_name === "/_list" ? { errcode: 0, apis: [...WIDE_SCOPE_APIS] }
      : body.api_name === "/shelf/sync" ? { errcode: 0, books: [] }
        : { errcode: 0, books: [{ bookId: "cursor-book", noteCount: 1, sort: undefined, book: { bookId: "cursor-book", title: "游标书" } }], hasMore: true, totalNoteCount: 1 };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  await assert.rejects(() => syncWeReadDataset(KEY, { fetchImpl, maxBooks: 100 }), error => error?.code === "PAGINATION");
});
