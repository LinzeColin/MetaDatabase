import { DEFAULT_CONCURRENCY, MAX_NOTEBOOK_PAGES, MAX_REVIEW_PAGES_PER_BOOK, MAX_SELECTED_BOOKS, NOTEBOOK_PAGE_SIZE, REVIEW_PAGE_SIZE } from "./constants.js";
import { UpgradeRequiredError, WeReadPortError, toSafeFailure } from "./errors.js";
import { assembleCanonicalBook, createSnapshot, normalizeBookInfo, normalizeBookmarkList, normalizeChapterInfo, normalizeNotebookPage, normalizeProgress, normalizeReadingStatistics, normalizeReviewPage } from "./normalize.js";

/** @typedef {(input:{key:string,apiName:string,params?:Record<string,unknown>,signal?:AbortSignal})=>Promise<Record<string,unknown>>} GatewayCaller */

/** @param {{key:string,call:GatewayCaller,signal?:AbortSignal,onProgress?:(message:string)=>void}} input */
export async function collectNotebookSummaries(input) {
  const all = [], seenBooks = new Set(), seenCursors = new Set();
  let lastSort;
  for (let page = 0; page < MAX_NOTEBOOK_PAGES; page += 1) {
    input.onProgress?.(`正在读取笔记本第 ${page + 1} 页…`);
    const params = lastSort === undefined ? { count: NOTEBOOK_PAGE_SIZE } : { count: NOTEBOOK_PAGE_SIZE, lastSort };
    const payload = await input.call({ key: input.key, apiName: "/user/notebooks", params, signal: input.signal });
    const normalized = normalizeNotebookPage(payload);
    for (const summary of normalized.summaries) if (!seenBooks.has(summary.bookId)) { seenBooks.add(summary.bookId); all.push(summary); }
    if (!normalized.hasMore) break;
    if (normalized.nextSort === undefined || normalized.nextSort === lastSort || seenCursors.has(normalized.nextSort)) throw new WeReadPortError("PAGINATION", "微信读书笔记本分页游标未前进，已停止以避免重复或死循环。");
    seenCursors.add(normalized.nextSort); lastSort = normalized.nextSort;
    if (page === MAX_NOTEBOOK_PAGES - 1) throw new WeReadPortError("PAGINATION", "微信读书笔记本分页超过安全上限。");
  }
  return all.sort((a, b) => b.totalNoteCount - a.totalNoteCount || a.title.localeCompare(b.title, "zh-CN") || a.bookId.localeCompare(b.bookId));
}

/** @param {{key:string,summaries:import('./model.js').NotebookSummary[],exportProfile:string,call:GatewayCaller,signal?:AbortSignal,concurrency?:number,includeReadingStatistics?:boolean,onProgress?:(done:number,total:number,title:string)=>void}} input */
export async function collectSnapshot(input) {
  if (!input.summaries.length) throw new WeReadPortError("NO_SELECTION", "请至少选择一本书。");
  if (input.summaries.length > MAX_SELECTED_BOOKS) throw new WeReadPortError("LIMIT", `一次最多导出 ${MAX_SELECTED_BOOKS} 本书。`);
  const internal = new AbortController();
  const signal = combineAbortSignals(input.signal, internal.signal);
  const books = [], failures = [];
  let done = 0;
  try {
    await mapConcurrent(input.summaries, input.concurrency ?? DEFAULT_CONCURRENCY, async summary => {
      try { books.push(await collectOneBook({ key: input.key, summary, call: input.call, signal })); }
      catch (error) {
        if (error instanceof UpgradeRequiredError) { internal.abort(error); throw error; }
        const safe = toSafeFailure(error); failures.push({ code: safe.code, message: safe.message, bookId: summary.bookId });
      } finally { done += 1; input.onProgress?.(done, input.summaries.length, summary.title); }
    }, signal);
  } catch (error) { if (error instanceof UpgradeRequiredError || internal.signal.reason instanceof UpgradeRequiredError) throw error instanceof UpgradeRequiredError ? error : internal.signal.reason; throw error; }
  if (!books.length && failures.length) throw new WeReadPortError("NO_EXPORTABLE_DATA", "所有选中书籍均读取失败，未生成误导性空导出。", { details: { failures } });
  let readingStatistics;
  if (input.includeReadingStatistics) {
    try { readingStatistics = normalizeReadingStatistics(await input.call({ key: input.key, apiName: "/readdata/detail", params: { mode: "overall" }, signal })); }
    catch (error) { if (error instanceof UpgradeRequiredError) throw error; failures.push({ code: "READING_STATS_UNAVAILABLE", message: "阅读统计暂不可用；书籍笔记仍已导出。" }); }
  }
  return createSnapshot(input.exportProfile, books, failures, readingStatistics);
}

/** @param {{key:string,summary:import('./model.js').NotebookSummary,call:GatewayCaller,signal?:AbortSignal}} input */
async function collectOneBook(input) {
  const bookId = input.summary.bookId;
  const warnings = [];
  const [bookmarkResponse, reviews, infoResult, chaptersResult, progressResult] = await Promise.all([
    input.call({ key: input.key, apiName: "/book/bookmarklist", params: { bookId }, signal: input.signal }),
    collectAllReviews(input.key, bookId, input.call, input.signal),
    optionalCall(input.call, { key: input.key, apiName: "/book/info", params: { bookId }, signal: input.signal }, "书籍详情", warnings),
    optionalCall(input.call, { key: input.key, apiName: "/book/chapterinfo", params: { bookId }, signal: input.signal }, "完整目录", warnings),
    optionalCall(input.call, { key: input.key, apiName: "/book/getprogress", params: { bookId }, signal: input.signal }, "阅读进度", warnings),
  ]);
  const bookmarks = normalizeBookmarkList(bookmarkResponse, bookId);
  const info = infoResult ? normalizeBookInfo(infoResult, input.summary) : undefined;
  const extraChapters = chaptersResult ? normalizeChapterInfo(chaptersResult) : undefined;
  const progress = progressResult ? normalizeProgress(progressResult, input.summary) : undefined;
  return assembleCanonicalBook({ overview: input.summary, info, progress, bookmarks, reviews, extraChapters, warnings });
}

/** @param {string} key @param {string} bookId @param {GatewayCaller} call @param {AbortSignal|undefined} signal */
async function collectAllReviews(key, bookId, call, signal) {
  const all = [], seenIds = new Set(), seenCursors = new Set();
  let synckey = 0;
  for (let page = 0; page < MAX_REVIEW_PAGES_PER_BOOK; page += 1) {
    const payload = await call({ key, apiName: "/review/list/mine", params: { bookid: bookId, synckey, count: REVIEW_PAGE_SIZE }, signal });
    const normalized = normalizeReviewPage(payload, bookId);
    for (const review of normalized.reviews) if (!seenIds.has(review.id)) { seenIds.add(review.id); all.push(review); }
    if (!normalized.hasMore) break;
    if (normalized.nextSyncKey === undefined || normalized.nextSyncKey === synckey || seenCursors.has(normalized.nextSyncKey)) throw new WeReadPortError("PAGINATION", `书籍 ${bookId} 的想法分页游标未前进，已停止。`);
    seenCursors.add(normalized.nextSyncKey); synckey = normalized.nextSyncKey;
    if (page === MAX_REVIEW_PAGES_PER_BOOK - 1) throw new WeReadPortError("PAGINATION", `书籍 ${bookId} 的想法分页超过安全上限。`);
  }
  return all.sort((a, b) => a.chapterIdx - b.chapterIdx || String(a.range ?? "").localeCompare(String(b.range ?? "")) || (a.createdAt ?? 0) - (b.createdAt ?? 0) || a.id.localeCompare(b.id));
}

/** @param {GatewayCaller} call @param {Parameters<GatewayCaller>[0]} request @param {string} label @param {string[]} warnings */
async function optionalCall(call, request, label, warnings) { try { return await call(request); } catch (error) { if (error instanceof UpgradeRequiredError) throw error; warnings.push(`${label}未读取；核心笔记内容不受影响。`); return undefined; } }

/** @template T,R @param {T[]} items @param {number} concurrency @param {(item:T,index:number)=>Promise<R>} worker @param {AbortSignal|undefined} signal */
export async function mapConcurrent(items, concurrency, worker, signal) {
  const limit = Math.max(1, Math.min(8, Math.floor(concurrency || 1))), results = new Array(items.length); let next = 0;
  async function run() { while (true) { if (signal?.aborted) throw signal.reason instanceof Error ? signal.reason : new WeReadPortError("CANCELLED", "操作已取消。"); const index = next++; if (index >= items.length) return; results[index] = await worker(items[index], index); } }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run)); return results;
}

/** @param {AbortSignal|undefined} first @param {AbortSignal} second */
function combineAbortSignals(first, second) { if (!first) return second; if (typeof AbortSignal.any === "function") return AbortSignal.any([first, second]); const controller = new AbortController(); const relay = signal => controller.abort(signal.reason); if (first.aborted) relay(first); else first.addEventListener("abort", () => relay(first), { once: true }); if (second.aborted) relay(second); else second.addEventListener("abort", () => relay(second), { once: true }); return controller.signal; }
