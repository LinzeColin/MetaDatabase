const GATEWAY = "https://i.weread.qq.com/api/agent/gateway";
const SKILL_VERSION = "1.0.4";
const MAX_RESPONSE_BYTES = 12 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 20_000;

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
} = {}) {
  validateWeReadKey(key);
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
  const details = await mapLimit(books, 3, async (entry, index) => {
    const bookId = String(entry.bookId || entry.book?.bookId || "");
    if (!bookId) return null;
    const [bookmarks, reviews, info, progress, chapters, popular] = await Promise.all([
      call("/book/bookmarklist", { bookId }),
      collectReviews(call, bookId),
      call("/book/info", { bookId }),
      call("/book/getprogress", { bookId }),
      call("/book/chapterinfo", { bookId }),
      index < popularBookLimit ? call("/book/bestbookmarks", { bookId, chapterUid: 0, synckey: 0 }) : null,
    ]);
    return { bookId, notebook: entry, bookmarks, reviews, info, progress, chapters, popularHighlights: popular };
  });

  const readingStats = {};
  for (const mode of ["weekly", "monthly", "annually", "overall"]) {
    readingStats[mode] = await call("/readdata/detail", { mode, baseTime: 0 });
  }

  const recommendations = [];
  let maxIdx = 0;
  for (let page = 0; page < recommendationPages; page += 1) {
    const result = await call("/book/recommend", { count: 20, maxIdx });
    const items = Array.isArray(result?.books) ? result.books : [];
    recommendations.push(...items);
    if (!items.length) break;
    const next = Number(items.at(-1)?.searchIdx ?? 0);
    if (!Number.isFinite(next) || next <= maxIdx) break;
    maxIdx = next;
  }

  const shelfBooks = Array.isArray(shelf?.books) ? shelf.books : [];
  const shelfAlbums = Array.isArray(shelf?.albums) ? shelf.albums : [];
  const shelfTotal = shelfBooks.length + shelfAlbums.length + (shelf?.mp ? 1 : 0);
  return {
    contract: { gateway: GATEWAY, skillVersion: SKILL_VERSION, scope: "full-supported-capability-discovery", maxBooks },
    capabilities,
    shelf: { ...shelf, computedTotal: shelfTotal },
    notebooks,
    books: details.filter(Boolean),
    readingStats,
    recommendations,
    failures,
    partial: failures.length > 0,
    summary: {
      shelfElectronicBooks: shelfBooks.length,
      shelfAlbums: shelfAlbums.length,
      shelfHasArticleCollection: Boolean(shelf?.mp),
      shelfTotal,
      notebookBooks: books.length,
      totalNoteCount: Number(notebooks.totalNoteCount || 0),
      detailedBooks: details.filter(Boolean).length,
      recommendationCount: recommendations.length,
      failedCalls: failures.length,
      truncatedBySafetyLimit: notebooks.truncated,
    },
  };
}

export function normalizeWeReadDocuments(dataset) {
  const documents = [];
  for (const item of dataset.books || []) {
    const title = item.info?.title || item.notebook?.book?.title || `微信读书 ${item.bookId}`;
    const author = item.info?.author || item.notebook?.book?.author || "";
    const chapters = new Map((item.bookmarks?.chapters || item.chapters?.chapters || []).map(chapter => [String(chapter.chapterUid), chapter.title || `章节 ${chapter.chapterIdx || ""}`]));
    for (const mark of item.bookmarks?.updated || []) {
      documents.push({
        externalId: `highlight:${mark.bookmarkId || `${item.bookId}:${mark.range || mark.createTime}`}`,
        source: "weread",
        title,
        category: item.info?.category || item.notebook?.book?.category || "微信读书",
        content: [`# ${title}`, author ? `作者：${author}` : "", chapters.get(String(mark.chapterUid)) ? `章节：${chapters.get(String(mark.chapterUid))}` : "", `> ${mark.markText || ""}`].filter(Boolean).join("\n\n"),
        createdAt: Number(mark.createTime || 0),
      });
    }
    for (const wrapper of item.reviews?.reviews || []) {
      const review = wrapper.review || wrapper;
      documents.push({
        externalId: `review:${review.reviewId || `${item.bookId}:${review.createTime || documents.length}`}`,
        source: "weread",
        title,
        category: item.info?.category || item.notebook?.book?.category || "微信读书",
        content: [`# ${title}`, author ? `作者：${author}` : "", review.chapterName ? `章节：${review.chapterName}` : "", review.abstract ? `> ${review.abstract}` : "", review.content || ""].filter(Boolean).join("\n\n"),
        createdAt: Number(review.createTime || 0),
      });
    }
  }
  return documents;
}

export function recommendationRows(dataset) {
  return (dataset.recommendations || []).map((book, index) => ({
    id: `weread:${book.bookId || index}`,
    source: "weread-official",
    title: String(book.title || "未命名书籍").slice(0, 180),
    author: book.author ? String(book.author).slice(0, 120) : null,
    reason: String(book.reason || "根据你的微信读书阅读记录推荐").slice(0, 240),
    deepLink: safeDeepLink(book.deepLink),
    score: Number(book.newRating || 0) + Math.log10(Math.max(1, Number(book.readingCount || 1))),
  }));
}

async function collectNotebooks(call, maxBooks) {
  const books = [];
  let lastSort;
  let totalNoteCount = 0;
  let page = 0;
  let truncated = false;
  while (page < 1000) {
    const params = { count: 100 };
    if (lastSort !== undefined) params.lastSort = lastSort;
    const result = await call("/user/notebooks", params, true);
    const current = Array.isArray(result?.books) ? result.books : [];
    books.push(...current);
    totalNoteCount = Number(result?.totalNoteCount ?? totalNoteCount);
    if (books.length >= maxBooks) { truncated = Boolean(result?.hasMore) || books.length > maxBooks; break; }
    if (!result?.hasMore || !current.length) break;
    const next = Number(current.at(-1)?.sort);
    if (!Number.isFinite(next) || next === lastSort) break;
    lastSort = next;
    page += 1;
  }
  return { books: books.slice(0, maxBooks), totalBookCount: books.length, totalNoteCount, truncated };
}

async function collectReviews(call, bookId) {
  const reviews = [];
  let synckey = 0;
  let page = 0;
  let totalCount = 0;
  while (page < 1000) {
    const result = await call("/review/list/mine", { bookid: bookId, synckey, count: 100 });
    if (!result) break;
    const current = Array.isArray(result.reviews) ? result.reviews : [];
    reviews.push(...current);
    totalCount = Number(result.totalCount ?? totalCount);
    if (!result.hasMore || !current.length) break;
    const next = Number(result.synckey);
    if (!Number.isFinite(next) || next === synckey) break;
    synckey = next;
    page += 1;
  }
  return { reviews, totalCount, synckey };
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

function safeDeepLink(value) {
  try { const url = new URL(String(value)); return ["https:", "weread:"].includes(url.protocol) ? url.toString() : null; }
  catch { return null; }
}
