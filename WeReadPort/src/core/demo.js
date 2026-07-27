/** 纯虚构演示数据；不对应任何真实用户、真实书籍或受版权保护的原文。 */
export const DEMO_NOTEBOOKS = Object.freeze([
  { bookId: "demo-book-001", title: "深海算法", author: "林屿", coverUrl: undefined, deepLink: undefined, reviewCount: 2, highlightCount: 3, bookmarkCount: 1, totalNoteCount: 6, readingProgress: 68, sort: 1785024000 },
  { bookId: "demo-book-002", title: "有限花园", author: "周遥", coverUrl: undefined, deepLink: undefined, reviewCount: 2, highlightCount: 2, bookmarkCount: 0, totalNoteCount: 4, readingProgress: 100, sort: 1784937600 },
]);

/** @returns {(input:{key:string,apiName:string,params?:Record<string,unknown>,signal?:AbortSignal})=>Promise<Record<string,unknown>>} */
export function createDemoCaller() {
  return async ({ apiName, params = {}, signal }) => {
    if (signal?.aborted) throw signal.reason;
    const bookId = String(params.bookId ?? params.bookid ?? "");
    if (apiName === "/user/notebooks") return { totalBookCount: 2, totalNoteCount: 10, hasMore: 0, books: DEMO_NOTEBOOKS.map(item => ({ bookId: item.bookId, book: { bookId: item.bookId, title: item.title, author: item.author }, reviewCount: item.reviewCount, noteCount: item.highlightCount, bookmarkCount: item.bookmarkCount, readingProgress: item.readingProgress, sort: item.sort })) };
    if (apiName === "/book/bookmarklist") return demoBookmarks(bookId);
    if (apiName === "/review/list/mine") return demoReviews(bookId);
    if (apiName === "/book/info") return demoInfo(bookId);
    if (apiName === "/book/getprogress") return bookId === "demo-book-001" ? { progress: 68, recordReadingTime: 9320, updateTime: 1785024000 } : { progress: 100, recordReadingTime: 14880, updateTime: 1784937600 };
    if (apiName === "/book/chapterinfo") return { chapters: demoChapters(bookId) };
    if (apiName === "/readdata/detail") return { mode: "overall", totalReadTime: 24200, readDays: 17, readStat: [{ stat: "读完", counts: "1本" }] };
    throw new Error(`演示环境不支持接口 ${apiName}`);
  };
}

/** @param {string} bookId */
function demoChapters(bookId) { return bookId === "demo-book-001" ? [{ chapterUid: "c1", chapterIdx: 1, title: "第一章：信号" }, { chapterUid: "c2", chapterIdx: 2, title: "第二章：边界" }] : [{ chapterUid: "g1", chapterIdx: 1, title: "种子" }, { chapterUid: "g2", chapterIdx: 2, title: "修剪" }]; }
/** @param {string} bookId */
function demoBookmarks(bookId) {
  const chapters = demoChapters(bookId);
  if (bookId === "demo-book-001") return { chapters, updated: [
    { bookmarkId: "h-001", bookId, chapterUid: "c1", chapterIdx: 1, markText: "信息的价值不在于数量，而在于它能否改变下一步行动。", createTime: 1784764800, type: 1, range: "120-150", colorStyle: 1 },
    { bookmarkId: "h-002", bookId, chapterUid: "c1", chapterIdx: 1, markText: "可靠系统会把不确定性暴露出来，而不是把它包装成确定。", createTime: 1784851200, type: 1, range: "310-352", colorStyle: 2 },
    { bookmarkId: "h-003", bookId, chapterUid: "c2", chapterIdx: 2, markText: "边界不是限制创造力，而是让责任可以被验证。", createTime: 1785024000, type: 1, range: "710-744", colorStyle: 3 },
  ] };
  return { chapters, updated: [
    { bookmarkId: "h-101", bookId, chapterUid: "g1", chapterIdx: 1, markText: "一座花园的秩序来自持续选择，而不是一次完成。", createTime: 1784505600, type: 1, range: "88-120", colorStyle: 1 },
    { bookmarkId: "h-102", bookId, chapterUid: "g2", chapterIdx: 2, markText: "删除并非损失；在明确目标后，删除也是一种设计。", createTime: 1784937600, type: 1, range: "502-541", colorStyle: 2 },
  ] };
}
/** @param {string} bookId */
function demoReviews(bookId) {
  if (bookId === "demo-book-001") return { totalCount: 2, hasMore: 0, synckey: 0, reviews: [
    { review: { reviewId: "r-001", content: "这句话可以直接转成验收标准：信息必须对应一个可观察的决策变化。", abstract: "信息的价值不在于数量，而在于它能否改变下一步行动。", range: "120-150", chapterUid: "c1", chapterIdx: 1, chapterName: "第一章：信号", createTime: 1784764900, star: -1 } },
    { review: { reviewId: "r-002", content: "全书最有用的提醒是：不要让成功状态掩盖部分失败。", chapterUid: "book", createTime: 1785024100, star: 4, isFinish: 0 } },
  ] };
  return { totalCount: 2, hasMore: 0, synckey: 0, reviews: [
    { review: { reviewId: "r-101", content: "适合用来理解产品范围管理：保留核心，主动剪掉无收益的复杂度。", abstract: "删除并非损失；在明确目标后，删除也是一种设计。", range: "502-541", chapterUid: "g2", chapterIdx: 2, chapterName: "修剪", createTime: 1784937700, star: -1 } },
    { review: { reviewId: "r-102", content: "读完后更清楚：长期维护不是额外工作，而是产品本身。", chapterUid: "book", createTime: 1784937800, star: 5, isFinish: 1 } },
  ] };
}
/** @param {string} bookId */
function demoInfo(bookId) { return bookId === "demo-book-001" ? { bookId, title: "深海算法", author: "林屿", publisher: "演示出版社", publishTime: "2026", category: "技术思考", intro: "一份完全虚构的演示书籍资料，用于验证导出流程。", newRating: 8.8 } : { bookId, title: "有限花园", author: "周遥", publisher: "演示出版社", publishTime: "2025", category: "系统设计", intro: "一份完全虚构的演示书籍资料，用于验证导出流程。", newRating: 9.1 }; }
