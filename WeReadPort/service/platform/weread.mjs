import {
  normalizeBookInfo,
  normalizeBookmarkList,
  normalizeChapterInfo,
  normalizeNotebookPage,
  normalizeProgress,
  normalizeReviewPage,
  unwrapGatewayData,
} from "../../src/core/normalize.js";

const GATEWAY = "https://i.weread.qq.com/api/agent/gateway";
const SKILL_VERSION = "1.0.4";
export const WEREAD_COLLECTION_FORMAT_VERSION = "2";
const MAX_RESPONSE_BYTES = 12 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 20_000;
const MIN_TRUSTED_SOURCE_TIME = 946_684_800; // 2000-01-01 UTC
const MAX_TRUSTED_SOURCE_TIME = 4_102_444_800; // 2100-01-01 UTC

export const WIDE_SCOPE_APIS = Object.freeze([
  "/_list",
  "/shelf/sync",
  "/user/notebooks",
  "/book/bookmarklist",
  "/review/list/mine",
  "/book/info",
  "/book/getprogress",
  "/book/chapterinfo",
  "/readdata/detail",
  "/book/recommend",
  "/book/similar",
  "/book/bestbookmarks",
  "/book/underlines",
  "/book/readreviews",
  "/review/single",
]);

export async function verifyWeReadKey(key, options = {}) {
  validateWeReadKey(key);
  const capabilities = await gatewayCall(key, "/_list", {}, options);
  return { valid: true, capabilities: extractCapabilities(capabilities) };
}

export async function syncWeReadDataset(key, {
  fetchImpl = fetch,
  maxBooks = 2000,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  popularBookLimit = 40,
  recommendationPages = 3,
  mode = "full",
  previousBookState = {},
} = {}) {
  validateWeReadKey(key);
  const syncMode = mode === "incremental" ? "incremental" : "full";
  const options = { fetchImpl, timeoutMs };
  const failures = [];
  const capabilityPayload = await gatewayCall(key, "/_list", {}, options);
  const capabilities = extractCapabilities(capabilityPayload);
  const supported = api => capabilities.length === 0 || capabilities.includes(api);
  const call = async (api, params = {}, required = false) => {
    if (!supported(api)) return null;
    try { return await gatewayCall(key, api, params, options); }
    catch (error) {
      failures.push({ api, code: error.code || "UPSTREAM", message: error.message });
      if (required) throw error;
      return null;
    }
  };

  const shelf = await call("/shelf/sync", {}, true);
  const notebooks = await collectNotebooks(call, maxBooks);
  const books = notebooks.books.slice(0, maxBooks);
  const priorState = isPlainObject(previousBookState) ? previousBookState : {};
  const candidates = books.map((entry, index) => {
    const bookId = notebookBookId(entry);
    const fingerprint = notebookFingerprint(entry);
    const previous = normalizeBookState(priorState[bookId]);
    const skip = syncMode === "incremental"
      && Boolean(bookId && fingerprint && previous?.fingerprint === fingerprint && Number.isInteger(previous.documentCount) && previous.documentCount >= 0);
    return { entry, index, bookId, fingerprint, previous, skip };
  }).filter(item => item.bookId);
  const detailedCandidates = candidates.filter(item => !item.skip);
  const details = await mapLimit(detailedCandidates, syncMode === "incremental" ? 4 : 3, async ({ entry, index, bookId }) => {
    const needMetadataFallback = !entry?.title;
    const [bookmarkPayload, reviews, infoPayload, progressPayload, chaptersPayload, popular] = await Promise.all([
      call("/book/bookmarklist", { bookId }),
      collectReviews(call, bookId),
      syncMode === "full" || needMetadataFallback ? call("/book/info", { bookId }) : null,
      syncMode === "full" ? call("/book/getprogress", { bookId }) : null,
      syncMode === "full" ? call("/book/chapterinfo", { bookId }) : null,
      syncMode === "full" && index < popularBookLimit ? call("/book/bestbookmarks", { bookId, chapterUid: 0, synckey: 0 }) : null,
    ]);
    const bookmarks = bookmarkPayload === null ? null : normalizeBookmarkPayload(bookmarkPayload, bookId);
    const info = infoPayload === null ? null : normalizeBookInfo(infoPayload, entry);
    const progress = progressPayload === null ? null : normalizeProgress(progressPayload, entry);
    const chapters = chaptersPayload === null ? null : normalizeChapterInfo(chaptersPayload);
    const coreComplete = (!supported("/book/bookmarklist") || bookmarkPayload !== null)
      && (!supported("/review/list/mine") || reviews?.complete === true);
    return { bookId, notebook: entry, bookmarks, reviews, info, progress, chapters, popularHighlights: popular, coreComplete };
  });
  const detailsByBookId = new Map(details.filter(Boolean).map(item => [item.bookId, item]));
  const bookState = {};
  for (const candidate of candidates) {
    const detail = detailsByBookId.get(candidate.bookId);
    if (candidate.skip && candidate.previous) {
      bookState[candidate.bookId] = candidate.previous;
      continue;
    }
    if (detail?.coreComplete && candidate.fingerprint) {
      bookState[candidate.bookId] = { fingerprint: candidate.fingerprint, documentCount: documentCountForDetail(detail) };
      continue;
    }
    bookState[candidate.bookId] = { fingerprint: candidate.fingerprint, documentCount: null };
  }

  const readingStats = {};
  if (syncMode === "full") {
    for (const statsMode of ["weekly", "monthly", "annually", "overall"]) {
      readingStats[statsMode] = await call("/readdata/detail", { mode: statsMode, baseTime: 0 });
    }
  }

  const recommendations = [];
  if (syncMode === "full") {
    let maxIdx = 0;
    for (let page = 0; page < recommendationPages; page += 1) {
      const result = await call("/book/recommend", { count: 20, maxIdx });
      const recommendationData = result ? unwrapGatewayData(result) : null;
      const items = Array.isArray(recommendationData?.books) ? recommendationData.books : [];
      recommendations.push(...items);
      if (!items.length) break;
      const next = Number(items.at(-1)?.searchIdx ?? 0);
      if (!Number.isFinite(next) || next <= maxIdx) break;
      maxIdx = next;
    }
  }

  const shelfData = unwrapGatewayData(shelf);
  const shelfBooks = Array.isArray(shelfData?.books) ? shelfData.books : [];
  const shelfAlbums = Array.isArray(shelfData?.albums) ? shelfData.albums : [];
  const shelfTotal = shelfBooks.length + shelfAlbums.length + (shelfData?.mp ? 1 : 0);
  const sourceHighlightCount = books.reduce((total, book) => total + Number(book.highlightCount || 0), 0);
  const sourceReviewCount = books.reduce((total, book) => total + Number(book.reviewCount || 0), 0);
  const sourceBookmarkCount = books.reduce((total, book) => total + Number(book.bookmarkCount || 0), 0);
  return {
    contract: { gateway: GATEWAY, skillVersion: SKILL_VERSION, scope: syncMode === "full" ? "full-supported-capability-discovery" : "incremental-notebook-delta", maxBooks },
    capabilities,
    shelf: { ...shelfData, computedTotal: shelfTotal },
    notebooks,
    books: details.filter(Boolean),
    bookState,
    readingStats,
    recommendations,
    recommendationsRefreshed: syncMode === "full",
    failures,
    partial: failures.length > 0,
    summary: {
      shelfElectronicBooks: shelfBooks.length,
      shelfAlbums: shelfAlbums.length,
      shelfHasArticleCollection: Boolean(shelfData?.mp),
      shelfTotal,
      notebookBooks: books.length,
      totalNoteCount: Number(notebooks.totalNoteCount || 0),
      sourceHighlightCount,
      sourceReviewCount,
      sourceBookmarkCount,
      sourceContentCount: sourceHighlightCount + sourceReviewCount,
      detailedBooks: details.filter(Boolean).length,
      skippedUnchangedBooks: candidates.filter(item => item.skip).length,
      skippedUnchangedDocuments: candidates.filter(item => item.skip).reduce((total, item) => total + Number(item.previous?.documentCount || 0), 0),
      recommendationCount: recommendations.length,
      failedCalls: failures.length,
      truncatedBySafetyLimit: notebooks.truncated,
      collectionFormatVersion: WEREAD_COLLECTION_FORMAT_VERSION,
      syncMode,
    },
  };
}

export function normalizeWeReadDocuments(dataset) {
  const documents = [];
  for (const item of dataset.books || []) {
    const title = item.info?.title || item.notebook?.title || `微信读书 ${item.bookId}`;
    const author = item.info?.author || item.notebook?.author || "";
    const chapters = new Map(allChapters(item).map(chapter => [String(chapter.uid ?? chapter.chapterUid), chapter.title || `章节 ${chapter.chapterIdx || ""}`]));
    for (const mark of detailHighlights(item)) {
      documents.push({
        externalId: `highlight:${mark.id || mark.bookmarkId || `${item.bookId}:${mark.range || mark.createdAt || mark.createTime}`}`,
        source: "weread",
        title: wereadNoteTitle(title, mark.text || mark.markText, "书摘"),
        category: item.info?.category || item.notebook?.category || "微信读书",
        content: [`# ${title}`, author ? `作者：${author}` : "", mark.chapterTitle || chapters.get(String(mark.chapterUid)) ? `章节：${mark.chapterTitle || chapters.get(String(mark.chapterUid))}` : "", `> ${mark.text || mark.markText || ""}`].filter(Boolean).join("\n\n"),
        eventAt: sourceEventAt(mark.sourceUpdatedAt, mark.createdAt, mark.updateTime, mark.createTime),
      });
    }
    for (const review of detailReviews(item)) {
      documents.push({
        externalId: `review:${review.id || review.reviewId || `${item.bookId}:${review.createdAt || review.createTime || documents.length}`}`,
        source: "weread",
        title: wereadNoteTitle(title, review.content || review.abstract, "想法"),
        category: item.info?.category || item.notebook?.category || "微信读书",
        content: [`# ${title}`, author ? `作者：${author}` : "", review.chapterTitle || review.chapterName ? `章节：${review.chapterTitle || review.chapterName}` : "", review.abstract ? `> ${review.abstract}` : "", review.content || ""].filter(Boolean).join("\n\n"),
        eventAt: sourceEventAt(review.sourceUpdatedAt, review.createdAt, review.updateTime, review.createTime),
      });
    }
  }
  return documents;
}

export function recommendationRows(dataset) {
  return (dataset.recommendations || []).map((book, index) => ({
    id: `weread:${recommendationBookId(book) || index}`,
    source: "weread-official",
    title: String(book.title || book.bookInfo?.title || "未命名书籍").slice(0, 180),
    author: book.author || book.bookInfo?.author ? String(book.author || book.bookInfo?.author).slice(0, 120) : null,
    reason: String(book.reason || "根据你的微信读书阅读记录推荐").slice(0, 240),
    deepLink: officialRecommendationLink(book),
    score: Number(book.newRating || 0) + Math.log10(Math.max(1, Number(book.readingCount || 1))),
  }));
}

async function collectNotebooks(call, maxBooks) {
  const books = [];
  const seenBooks = new Set();
  const seenCursors = new Set();
  let lastSort;
  let totalNoteCount = 0;
  let totalBookCount = 0;
  let page = 0;
  let truncated = false;
  while (page < 1000) {
    const params = { count: 100 };
    if (lastSort !== undefined) params.lastSort = lastSort;
    const result = await call("/user/notebooks", params, true);
    const normalized = normalizeNotebookPage(result);
    for (const book of normalized.summaries) if (!seenBooks.has(book.bookId)) { seenBooks.add(book.bookId); books.push(book); }
    totalNoteCount = Number(normalized.totalNoteCount ?? totalNoteCount);
    totalBookCount = Number(normalized.totalBookCount ?? totalBookCount);
    if (books.length >= maxBooks) { truncated = Boolean(normalized.hasMore) || books.length > maxBooks; break; }
    if (!normalized.hasMore) break;
    const next = Number(normalized.nextSort);
    if (!Number.isFinite(next) || next === lastSort || seenCursors.has(next)) throw paginationError("微信读书笔记本分页游标未前进，已停止以避免遗漏或重复。");
    seenCursors.add(next);
    lastSort = next;
    page += 1;
  }
  if (page >= 1000) throw paginationError("微信读书笔记本分页超过安全上限，未将不完整结果写入账户。");
  return { books: books.slice(0, maxBooks), totalBookCount: totalBookCount || books.length, totalNoteCount, truncated };
}

async function collectReviews(call, bookId) {
  const reviews = [];
  const seenReviews = new Set();
  const seenCursors = new Set();
  let synckey = 0;
  let page = 0;
  let totalCount = 0;
  let complete = true;
  while (page < 1000) {
    const result = await call("/review/list/mine", { bookid: bookId, synckey, count: 100 });
    if (!result) { complete = false; break; }
    const normalized = normalizeReviewPayload(result, bookId);
    for (const review of normalized.reviews) if (!seenReviews.has(review.id)) { seenReviews.add(review.id); reviews.push(review); }
    totalCount = Number(normalized.totalCount ?? totalCount);
    if (!normalized.hasMore) break;
    const next = Number(normalized.nextSyncKey);
    if (!Number.isFinite(next) || next === synckey || seenCursors.has(next)) { complete = false; throw paginationError(`书籍 ${bookId} 的想法分页游标未前进，未将不完整数据视为完整。`); }
    seenCursors.add(next);
    synckey = next;
    page += 1;
  }
  if (page >= 1000) throw paginationError(`书籍 ${bookId} 的想法分页超过安全上限，未将不完整数据写入账户。`);
  return { reviews, totalCount, synckey, complete };
}

export async function gatewayCall(key, apiName, params = {}, { fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  validateWeReadKey(key);
  if (!WIDE_SCOPE_APIS.includes(apiName)) throw Object.assign(new Error("接口不在已审阅范围内。"), { code: "UNREVIEWED_API" });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error("微信读书接口超时。")), timeoutMs);
  try {
    const response = await fetchImpl(GATEWAY, {
      method: "POST",
      redirect: "manual",
      signal: controller.signal,
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json", Accept: "application/json", "User-Agent": "WeReadPort/0.0.0.1.9" },
      body: JSON.stringify({ api_name: apiName, skill_version: SKILL_VERSION, ...params }),
    });
    if (response.status >= 300 && response.status < 400) throw Object.assign(new Error("微信读书接口返回了不安全重定向。"), { code: "UPSTREAM_REDIRECT" });
    const length = Number(response.headers.get("content-length") || 0);
    if (length > MAX_RESPONSE_BYTES) throw Object.assign(new Error("微信读书响应超过安全上限。"), { code: "TOO_LARGE" });
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length > MAX_RESPONSE_BYTES) throw Object.assign(new Error("微信读书响应超过安全上限。"), { code: "TOO_LARGE" });
    let payload;
    try { payload = JSON.parse(bytes.toString("utf8") || "{}"); } catch { throw Object.assign(new Error("微信读书返回了无效 JSON。"), { code: "SCHEMA" }); }
    if (payload?.upgrade_info) throw Object.assign(new Error("微信读书接口协议需要升级，已安全停止。"), { code: "UPGRADE_REQUIRED", upgradeInfo: payload.upgrade_info });
    if (!response.ok || Number(payload?.errcode || 0) !== 0) throw Object.assign(new Error("微信读书授权或接口调用失败。"), { code: response.status === 401 || response.status === 403 ? "AUTH" : "UPSTREAM", status: response.status });
    return payload;
  } catch (error) {
    if (controller.signal.aborted) throw Object.assign(new Error("微信读书接口超时。"), { code: "TIMEOUT" });
    throw error;
  } finally { clearTimeout(timeout); }
}

export function validateWeReadKey(value) {
  const key = String(value ?? "").trim();
  if (!/^wrk-[A-Za-z0-9_-]{20,256}$/.test(key)) throw Object.assign(new Error("微信读书密钥格式无效。"), { code: "INVALID_KEY" });
  return key;
}

function extractCapabilities(payload) {
  const candidates = [payload?.apis, payload?.api_list, payload?.data?.apis, payload?.data, payload];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return [...new Set(candidate.map(item => typeof item === "string" ? item : item?.api_name || item?.name).filter(value => typeof value === "string" && value.startsWith("/")))];
    }
  }
  return [];
}

async function mapLimit(items, limit, mapper) {
  const output = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (true) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      output[index] = await mapper(items[index], index);
    }
  });
  await Promise.all(workers);
  return output;
}

function notebookBookId(entry) {
  return String(entry?.bookId || entry?.book?.bookId || "").trim();
}

function notebookFingerprint(entry) {
  const book = entry?.book || {};
  const sourceTime = trustedSourceTime(
    entry?.updateTime, entry?.updatedAt, entry?.modifiedTime, entry?.lastUpdateTime,
    book?.updateTime, book?.updatedAt, entry?.sort,
  );
  if (!sourceTime) return null;
  return JSON.stringify({
    sourceTime,
    highlights: nonNegativeInteger(entry?.highlightCount ?? entry?.noteCount ?? entry?.note_count),
    reviews: nonNegativeInteger(entry?.reviewCount ?? entry?.review_count),
    bookmarks: nonNegativeInteger(entry?.bookmarkCount ?? entry?.bookmark_count),
    progress: normalizedProgress(entry?.readingProgress ?? entry?.progress),
  });
}

function normalizeBookState(value) {
  if (!isPlainObject(value) || typeof value.fingerprint !== "string") return null;
  const documentCount = Number(value.documentCount);
  return { fingerprint: value.fingerprint, documentCount: Number.isInteger(documentCount) && documentCount >= 0 ? documentCount : null };
}

function documentCountForDetail(detail) {
  return detailHighlights(detail).length + detailReviews(detail).length;
}

function allChapters(detail) {
  const chapters = [detail?.bookmarks?.chapters, detail?.chapters?.chapters, detail?.chapters]
    .filter(Array.isArray)
    .flat();
  const seen = new Set();
  return chapters.filter(chapter => {
    const id = String(chapter?.uid ?? chapter?.chapterUid ?? "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function detailHighlights(detail) {
  if (Array.isArray(detail?.bookmarks?.highlights)) return detail.bookmarks.highlights;
  return Array.isArray(detail?.bookmarks?.updated) ? detail.bookmarks.updated : [];
}

function detailReviews(detail) {
  if (Array.isArray(detail?.reviews?.reviews)) return detail.reviews.reviews;
  return Array.isArray(detail?.reviews) ? detail.reviews : [];
}

function normalizeBookmarkPayload(payload, bookId) {
  const normalized = normalizeBookmarkList(payload, bookId);
  const data = unwrapGatewayData(payload);
  const rawRows = [data?.updated, data?.bookmarks, data?.bookmarkList].find(Array.isArray) || [];
  const byId = new Map(rawRows.map(row => [sourceItemId(row, "bookmarkId"), row]).filter(([id]) => id));
  return {
    ...normalized,
    highlights: normalized.highlights.map(highlight => {
      const raw = byId.get(String(highlight.id));
      return { ...highlight, sourceUpdatedAt: sourceEventAt(raw?.updateTime, raw?.updatedAt, highlight.createdAt) };
    }),
  };
}

function normalizeReviewPayload(payload, bookId) {
  const normalized = normalizeReviewPage(payload, bookId);
  const data = unwrapGatewayData(payload);
  const rawRows = [data?.reviews, data?.reviewList, data?.updated].find(Array.isArray) || [];
  const byId = new Map(rawRows.map(row => [sourceItemId(row?.review || row, "reviewId"), row]).filter(([id]) => id));
  return {
    ...normalized,
    reviews: normalized.reviews.map(review => {
      const raw = byId.get(String(review.id));
      const body = raw?.review || raw;
      return { ...review, sourceUpdatedAt: sourceEventAt(body?.updateTime, body?.updatedAt, review.createdAt) };
    }),
  };
}

function sourceItemId(row, preferred) { return String(row?.[preferred] || row?.id || "").trim(); }

function recommendationBookId(book) {
  return String(book?.bookId || book?.bookInfo?.bookId || book?.id || "").trim();
}

function officialRecommendationLink(book) {
  const supplied = safeOfficialWebLink(book?.deepLink || book?.deeplink || book?.url || book?.bookInfo?.deepLink);
  if (supplied) return supplied;
  const bookId = recommendationBookId(book);
  return /^[A-Za-z0-9_-]{6,256}$/.test(bookId) ? `https://weread.qq.com/web/bookDetail/${encodeURIComponent(bookId)}` : null;
}

function safeOfficialWebLink(value) {
  try {
    const url = new URL(String(value));
    return url.protocol === "https:" && url.hostname === "weread.qq.com" && url.pathname.startsWith("/web/") ? url.toString() : null;
  } catch { return null; }
}

function paginationError(message) { return Object.assign(new Error(message), { code: "PAGINATION" }); }

function wereadNoteTitle(bookTitle, detail, kind) {
  const book = compactText(bookTitle || "微信读书").slice(0, 48);
  const excerpt = compactText(detail).slice(0, 96);
  return `${kind}｜《${book || "微信读书"}》${excerpt ? ` · ${excerpt}` : ""}`.slice(0, 180);
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function trustedSourceTime(...values) {
  const seconds = sourceEventAt(...values);
  return seconds >= MIN_TRUSTED_SOURCE_TIME && seconds <= MAX_TRUSTED_SOURCE_TIME ? seconds : null;
}

function nonNegativeInteger(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.floor(number) : null;
}

function normalizedProgress(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? Math.round(number * 1000) / 1000 : null;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sourceEventAt(...values) {
  for (const value of values) {
    const raw = Number(value);
    if (!Number.isFinite(raw) || raw <= 0) continue;
    const seconds = raw >= 10_000_000_000 ? Math.floor(raw / 1000) : Math.floor(raw);
    if (seconds > 0) return seconds;
  }
  return null;
}
