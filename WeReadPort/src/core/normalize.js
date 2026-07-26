import { CANONICAL_SCHEMA_VERSION, SOURCE_SKILL_VERSION } from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { asArray, asFiniteNumber, asObject, asOptionalBoolean, asOptionalInteger, clampOptional, fnv1a32Hex, isPlainObject, maxFinite, normalizeText, unixSecondsToIsoDate } from "./util.js";

/** @param {unknown} response */
export function unwrapGatewayData(response) {
  const object = asObject(response, "Gateway response");
  if (isPlainObject(object.data)) return /** @type {Record<string,unknown>} */ (object.data);
  if (isPlainObject(object.result)) return /** @type {Record<string,unknown>} */ (object.result);
  return object;
}

/** @param {unknown} response */
export function normalizeNotebookPage(response) {
  const data = unwrapGatewayData(response);
  const rows = asArray(data.books ?? data.notebooks ?? data.booklist);
  const summaries = rows.map(normalizeNotebookSummary).filter(Boolean);
  const hasMore = asOptionalBoolean(data.hasMore ?? data.has_more) ?? false;
  const explicitCursor = asOptionalInteger(data.lastSort ?? data.last_sort ?? data.nextSort);
  const rowCursor = summaries.length ? summaries[summaries.length - 1].sort : undefined;
  return {
    summaries,
    totalBookCount: nonNegativeOptional(data.totalBookCount),
    totalNoteCount: nonNegativeOptional(data.totalNoteCount),
    hasMore,
    nextSort: explicitCursor ?? rowCursor,
  };
}

/** @param {unknown} row @returns {import('./model.js').NotebookSummary|undefined} */
export function normalizeNotebookSummary(row) {
  if (!isPlainObject(row)) return undefined;
  const book = isPlainObject(row.book) ? row.book : row;
  const bookId = firstString(row.bookId, book.bookId, row.id, book.id);
  if (!bookId) return undefined;
  const reviewCount = nonNegativeNumber(row.reviewCount ?? row.review_count);
  const highlightCount = nonNegativeNumber(row.noteCount ?? row.note_count);
  const bookmarkCount = nonNegativeNumber(row.bookmarkCount ?? row.bookmark_count);
  return {
    bookId,
    title: clean(firstString(book.title, row.title) || "未命名书籍"),
    author: clean(firstString(book.author, row.author)),
    coverUrl: safeRemoteUrl(firstString(book.cover, book.coverUrl, row.cover)),
    deepLink: safeSourceLink(firstString(book.deepLink, book.deeplink, row.deepLink)),
    reviewCount,
    highlightCount,
    bookmarkCount,
    totalNoteCount: reviewCount + highlightCount + bookmarkCount,
    readingProgress: clampOptional(row.readingProgress ?? row.progress, 0, 100),
    sort: nonNegativeOptional(row.sort ?? row.updateTime ?? row.updatedAt),
  };
}

/** @param {unknown} response @param {string} bookId */
export function normalizeBookmarkList(response, bookId) {
  const data = unwrapGatewayData(response);
  const chapters = asArray(data.chapters ?? data.chapterInfos ?? data.chapterList).map(normalizeChapter).filter(Boolean);
  const chapterByUid = new Map(chapters.map(chapter => [String(chapter.uid), chapter]));
  const highlights = asArray(data.updated ?? data.bookmarks ?? data.bookmarkList)
    .map((row, index) => normalizeHighlight(row, bookId, chapterByUid, index)).filter(Boolean);
  highlights.sort(compareContent);
  return { highlights, chapters, book: isPlainObject(data.book) ? data.book : undefined };
}

/** @param {unknown} response */
export function normalizeChapterInfo(response) {
  const data = unwrapGatewayData(response);
  const rows = asArray(data.chapters ?? data.chapterInfos ?? data.chapterList ?? data.updated);
  return rows.map(normalizeChapter).filter(Boolean).sort((a, b) => a.chapterIdx - b.chapterIdx || a.title.localeCompare(b.title, "zh-CN"));
}

/** @param {unknown} row @param {number} index */
function normalizeChapter(row, index = 0) {
  if (!isPlainObject(row)) return undefined;
  const uid = firstString(row.chapterUid, row.uid, row.chapterId) || String(asOptionalInteger(row.chapterUid ?? row.uid) ?? index + 1);
  return {
    uid,
    title: clean(firstString(row.title, row.chapterTitle, row.name) || `章节 ${index + 1}`),
    level: asOptionalInteger(row.level) ?? 1,
    chapterIdx: asOptionalInteger(row.chapterIdx ?? row.index ?? row.idx) ?? index,
  };
}

/** @param {unknown} row @param {string} bookId @param {Map<string,{uid:string,title:string,level:number,chapterIdx:number}>} chapterByUid @param {number} index */
function normalizeHighlight(row, bookId, chapterByUid, index) {
  if (!isPlainObject(row)) return undefined;
  if (row.type === 0) return undefined;
  const text = clean(firstString(row.markText, row.text, row.content));
  if (!text) return undefined;
  const chapterUid = firstString(row.chapterUid, row.chapterId) || String(asOptionalInteger(row.chapterUid) ?? "unknown");
  const chapter = chapterByUid.get(chapterUid);
  const range = firstString(row.range, row.rangeString, row.position);
  const createdAt = nonNegativeOptional(row.createTime ?? row.createdAt ?? row.updateTime);
  const id = firstString(row.bookmarkId, row.id) || `h-${fnv1a32Hex(`${bookId}\u0000${chapterUid}\u0000${range}\u0000${text}\u0000${createdAt ?? index}`)}`;
  return {
    id, sourceId: id, text, chapterUid,
    chapterTitle: chapter?.title ?? (clean(firstString(row.chapterName, row.chapterTitle)) || "未分章"),
    chapterIdx: chapter?.chapterIdx ?? asOptionalInteger(row.chapterIdx ?? row.chapterIndex) ?? Number.MAX_SAFE_INTEGER,
    range: range || undefined,
    createdAt,
    createdAtIso: unixSecondsToIsoDate(createdAt),
    colorStyle: asOptionalInteger(row.colorStyle ?? row.color),
    sourceIndex: index,
  };
}

/** @param {unknown} response @param {string} bookId */
export function normalizeReviewPage(response, bookId) {
  const data = unwrapGatewayData(response);
  const reviews = asArray(data.reviews ?? data.reviewList ?? data.updated)
    .map((row, index) => normalizeReview(row, bookId, index)).filter(Boolean);
  reviews.sort(compareContent);
  return {
    reviews,
    totalCount: nonNegativeOptional(data.totalCount),
    hasMore: asOptionalBoolean(data.hasMore ?? data.has_more) ?? false,
    nextSyncKey: asOptionalInteger(data.synckey ?? data.syncKey ?? data.nextSyncKey),
  };
}

/** @param {unknown} row @param {string} bookId @param {number} index */
function normalizeReview(row, bookId, index) {
  if (!isPlainObject(row)) return undefined;
  const review = isPlainObject(row.review) ? row.review : row;
  const content = clean(firstString(review.content, review.text));
  if (!content) return undefined;
  const abstract = clean(firstString(review.abstract, review.markText));
  const range = firstString(review.range, review.position);
  const chapterUid = firstIdentifier(review.chapterUid, row.chapterUid) || "book";
  const chapterTitle = clean(firstString(review.chapterName, review.chapterTitle, row.chapterName)) || (chapterUid === "book" ? "整本书" : "未分章");
  const chapterIdx = asOptionalInteger(review.chapterIdx ?? row.chapterIdx) ?? (chapterUid === "book" ? Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER - 1);
  const createdAt = nonNegativeOptional(review.createTime ?? review.createdAt ?? review.updateTime);
  const starRaw = asFiniteNumber(review.star, -1);
  const star = starRaw >= 0 && starRaw <= 5 ? starRaw : undefined;
  const finish = asOptionalBoolean(review.isFinish);
  const id = firstString(review.reviewId, review.id) || `r-${fnv1a32Hex(`${bookId}\u0000${chapterUid}\u0000${range}\u0000${content}\u0000${createdAt ?? index}`)}`;
  const kind = abstract || range ? "highlight-thought" : chapterUid !== "book" || chapterTitle !== "整本书" ? "chapter-comment" : finish !== undefined || star !== undefined ? "book-review" : "unclassified";
  return {
    id, sourceId: id, content, abstract: abstract || undefined, range: range || undefined,
    chapterUid, chapterTitle, chapterIdx, createdAt, createdAtIso: unixSecondsToIsoDate(createdAt),
    star, isFinish: finish, kind, sourceIndex: index,
  };
}

/** @param {unknown} response @param {import('./model.js').NotebookSummary} overview */
export function normalizeBookInfo(response, overview) {
  const value = unwrapGatewayData(response);
  const data = isPlainObject(value.book) ? value.book : value;
  const id = firstString(data.bookId, overview.bookId);
  if (!id) throw new WeReadPortError("SCHEMA", "书籍信息缺少 bookId。");
  return {
    id,
    title: clean(firstString(data.title, overview.title) || "未命名书籍"),
    author: clean(firstString(data.author, overview.author)),
    translator: clean(firstString(data.translator)),
    coverUrl: safeRemoteUrl(firstString(data.cover, data.coverUrl, overview.coverUrl)),
    deepLink: safeSourceLink(firstString(data.deepLink, data.deeplink, overview.deepLink)),
    intro: clean(firstString(data.intro, data.description)),
    category: normalizeCategory(data.category),
    publisher: clean(firstString(data.publisher)),
    publishTime: clean(firstString(data.publishTime, data.publishDate)),
    isbn: clean(firstString(data.isbn)),
    wordCount: asOptionalInteger(data.wordCount),
    rating: positiveOptional(data.newRating ?? data.rating ?? data.ratings),
  };
}

/** @param {unknown} response @param {import('./model.js').NotebookSummary} overview */
export function normalizeProgress(response, overview) {
  const root = unwrapGatewayData(response);
  const data = isPlainObject(root.book) ? root.book : root;
  return {
    progress: clampOptional(data.progress ?? data.readingProgress ?? overview.readingProgress, 0, 100),
    readingTimeSeconds: nonNegativeOptional(data.recordReadingTime ?? data.readingTime ?? data.readingTimeSeconds),
    updateTime: nonNegativeOptional(data.updateTime ?? data.readUpdateTime ?? data.readingTimeUpdatedAt),
  };
}

/** @param {unknown} response */
export function normalizeReadingStatistics(response) {
  const data = unwrapGatewayData(response);
  // The official Skill currently documents totalReadTime/readDays/readStat. Keep
  // reviewed aliases for backward-compatible responses, but never infer missing data.
  const totalReadingTimeSeconds = nonNegativeOptional(data.totalReadTime ?? data.totalReadingTime ?? data.readingTime ?? data.readingTimeSeconds);
  const totalReadingDays = nonNegativeOptional(data.readDays ?? data.totalReadingDays ?? data.readingDays);
  const totalFinishedBooks = nonNegativeOptional(data.totalFinishedBooks ?? data.finishedBookCount ?? data.finishedBooks) ?? finishedBooksFromReadStat(data.readStat);
  return { mode: firstString(data.mode) || "overall", totalReadingTimeSeconds, totalReadingDays, totalFinishedBooks };
}

/** @param {{overview:import('./model.js').NotebookSummary,info?:ReturnType<typeof normalizeBookInfo>,progress?:ReturnType<typeof normalizeProgress>,bookmarks:ReturnType<typeof normalizeBookmarkList>,reviews:ReturnType<typeof normalizeReviewPage>["reviews"],extraChapters?:ReturnType<typeof normalizeChapterInfo>,warnings?:string[]}} input */
export function assembleCanonicalBook(input) {
  const info = input.info ?? {
    id: input.overview.bookId, title: input.overview.title, author: input.overview.author, translator: "",
    coverUrl: input.overview.coverUrl ?? "", deepLink: input.overview.deepLink ?? "", intro: "", category: "", publisher: "", publishTime: "", isbn: "", wordCount: undefined, rating: undefined,
  };
  const chapters = mergeChapters([...input.bookmarks.chapters, ...(input.extraChapters ?? [])], input.bookmarks.highlights, input.reviews);
  const sourceTimestamp = maxFinite([...input.bookmarks.highlights.map(item => item.createdAt), ...input.reviews.map(item => item.createdAt), input.progress?.updateTime, input.overview.sort]);
  const warnings = new Set(input.warnings ?? []);
  if (input.bookmarks.highlights.length !== input.overview.highlightCount) warnings.add(`概览划线数 ${input.overview.highlightCount}，本次可导出划线 ${input.bookmarks.highlights.length}。`);
  if (input.reviews.length !== input.overview.reviewCount) warnings.add(`概览想法/点评数 ${input.overview.reviewCount}，本次可导出 ${input.reviews.length}。`);
  if (input.overview.bookmarkCount > 0) warnings.add(`书签仅计数 ${input.overview.bookmarkCount} 条；官方当前接口不返回书签正文。`);
  return {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: { provider: "WeChat Reading", bookId: input.overview.bookId, skillVersion: SOURCE_SKILL_VERSION },
    metadata: info,
    counts: {
      highlights: input.bookmarks.highlights.length,
      thoughtsAndReviews: input.reviews.length,
      officialHighlightCount: input.overview.highlightCount,
      officialReviewCount: input.overview.reviewCount,
      officialBookmarkCount: input.overview.bookmarkCount,
    },
    progress: input.progress ?? { progress: input.overview.readingProgress, readingTimeSeconds: undefined, updateTime: undefined },
    chapters, highlights: input.bookmarks.highlights, thoughts: input.reviews,
    sourceSnapshotAt: sourceTimestamp, sourceSnapshotAtIso: unixSecondsToIsoDate(sourceTimestamp),
    warnings: Array.from(warnings).sort((a, b) => a.localeCompare(b, "zh-CN")),
  };
}

/** @param {string} exportProfile @param {import('./model.js').CanonicalBook[]} books @param {Array<{code:string,message:string,bookId?:string}>} failures @param {Record<string,unknown>|undefined} readingStatistics */
export function createSnapshot(exportProfile, books, failures, readingStatistics) {
  return {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: "WeChat Reading official Agent API Gateway",
    sourceSkillVersion: SOURCE_SKILL_VERSION,
    exportProfile,
    books: [...books].sort((a, b) => a.metadata.title.localeCompare(b.metadata.title, "zh-CN") || a.source.bookId.localeCompare(b.source.bookId)),
    failures: [...failures].sort((a, b) => String(a.bookId ?? "").localeCompare(String(b.bookId ?? "")) || a.code.localeCompare(b.code)),
    readingStatistics,
  };
}

/** @param {Array<{uid:string,title:string,level:number,chapterIdx:number}>} chapters @param {Array<Record<string,unknown>>} highlights @param {Array<Record<string,unknown>>} thoughts */
function mergeChapters(chapters, highlights, thoughts) {
  const byUid = new Map();
  for (const chapter of chapters) if (!byUid.has(chapter.uid)) byUid.set(chapter.uid, chapter);
  for (const item of [...highlights, ...thoughts]) {
    const uid = String(item.chapterUid ?? "unknown");
    if (!byUid.has(uid)) byUid.set(uid, { uid, title: String(item.chapterTitle ?? "未分章"), level: 1, chapterIdx: typeof item.chapterIdx === "number" ? item.chapterIdx : Number.MAX_SAFE_INTEGER });
  }
  return Array.from(byUid.values()).sort((a, b) => a.chapterIdx - b.chapterIdx || a.title.localeCompare(b.title, "zh-CN") || a.uid.localeCompare(b.uid));
}
/** @param {Record<string,unknown>} a @param {Record<string,unknown>} b */
function compareContent(a, b) { return (Number(a.chapterIdx) - Number(b.chapterIdx)) || compareRange(String(a.range ?? ""), String(b.range ?? "")) || (Number(a.createdAt ?? 0) - Number(b.createdAt ?? 0)) || String(a.id).localeCompare(String(b.id)); }
/** @param {string} a @param {string} b */
function compareRange(a, b) { const an = Number.parseInt(a.split("-")[0] ?? "", 10), bn = Number.parseInt(b.split("-")[0] ?? "", 10); if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return an - bn; return a.localeCompare(b); }
/** @param {...unknown} values */
function firstString(...values) { for (const value of values) if (typeof value === "string" && value.trim()) return value.trim(); return ""; }
/** @param {...unknown} values */
function firstIdentifier(...values) { for (const value of values) { if (typeof value === "string" && value.trim()) return value.trim(); if (typeof value === "number" && Number.isFinite(value)) return String(value); } return ""; }
/** @param {unknown} value */
function normalizeCategory(value) { if (Array.isArray(value)) return value.map(item => typeof item === "string" ? clean(item) : "").filter(Boolean).join(" / "); return clean(firstString(value)); }
/** @param {string} value */
function clean(value) { return value ? normalizeText(value) : ""; }
/** @param {unknown} value */
function nonNegativeNumber(value) { const n = asFiniteNumber(value, 0); return n >= 0 ? n : 0; }
/** @param {unknown} value */
function nonNegativeOptional(value) {
  const number = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}
/** @param {unknown} value */
function positiveOptional(value) {
  const number = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(number) && number > 0 ? number : undefined;
}
/** @param {unknown} value */
function finishedBooksFromReadStat(value) {
  for (const row of asArray(value)) {
    if (!isPlainObject(row)) continue;
    const label = firstString(row.stat, row.name, row.title, row.label);
    if (!label.includes("读完") && !/finish/i.test(label)) continue;
    const direct = nonNegativeOptional(row.count ?? row.bookCount ?? row.value);
    if (direct !== undefined) return direct;
    const text = firstString(row.counts, row.summary, row.valueText);
    const match = text.match(/(\d+(?:\.\d+)?)/);
    if (match) return Number(match[1]);
  }
  return undefined;
}
/** @param {string} value */
function safeRemoteUrl(value) { if (!value) return ""; try { const url = new URL(value); return url.protocol === "https:" ? url.toString() : ""; } catch { return ""; } }
/** @param {string} value */
function safeSourceLink(value) { if (!value) return ""; try { const url = new URL(value); return ["https:", "weread:"].includes(url.protocol) ? value : ""; } catch { return ""; } }
