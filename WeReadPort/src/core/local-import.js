import {
  CANONICAL_SCHEMA_VERSION,
  LOCAL_IMPORT_CONTRACT_VERSION,
  MAX_LOCAL_IMPORT_FILE_BYTES,
  MAX_LOCAL_IMPORT_FILES,
  MAX_LOCAL_IMPORT_TOTAL_BYTES,
  MAX_PREVIOUS_ARCHIVE_BYTES,
} from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { loadPreviousExport } from "./exporter.js";
import { decodeUtf8, isPlainObject, normalizeText, sha256Hex } from "./util.js";

const TEXT_EXTENSIONS = new Set(["md", "markdown", "txt"]);
const MAX_BOOKS = 2_000;
const MAX_ITEMS_PER_BOOK = 100_000;
const MAX_TEXT_CHARS = 2_000_000;

/**
 * 将一个受支持的本地选择转换为规范化阅读快照。
 * 读取发生在浏览器 Worker 中，不向服务端上传文件。
 * @param {Array<{name:string,type?:string,size?:number,bytes:ArrayBuffer|Uint8Array}>} inputFiles
 */
export async function importLocalFiles(inputFiles) {
  const files = normalizeFiles(inputFiles);
  const kind = classifySelection(files);
  if (kind === "archive") return importArchive(files[0]);
  if (kind === "canonical") return importCanonicalJson(files[0]);
  return importTextFiles(files);
}

/** 只校验文件名、数量与声明大小，供主线程在读取字节前快速反馈。 */
export function validateLocalFileDescriptors(inputFiles) {
  const files = (Array.isArray(inputFiles) ? inputFiles : []).map(file => ({
    name: String(file?.name ?? ""),
    size: Number(file?.size ?? 0),
    type: String(file?.type ?? ""),
    bytes: new Uint8Array(0),
  }));
  classifySelection(files, { descriptorsOnly: true });
  return true;
}

function normalizeFiles(inputFiles) {
  if (!Array.isArray(inputFiles) || !inputFiles.length) throw new WeReadPortError("LOCAL_IMPORT", "请选择要读取的本地笔记文件。");
  return inputFiles.map((file, index) => {
    const name = String(file?.name ?? "").normalize("NFC").trim();
    const bytes = file?.bytes instanceof Uint8Array ? file.bytes : file?.bytes instanceof ArrayBuffer ? new Uint8Array(file.bytes) : undefined;
    if (!name || !bytes) throw new WeReadPortError("LOCAL_IMPORT", `第 ${index + 1} 个本地文件缺少名称或内容。`);
    return { name, type: String(file?.type ?? ""), size: bytes.byteLength, bytes };
  });
}

function classifySelection(files, options = {}) {
  if (!files.length) throw new WeReadPortError("LOCAL_IMPORT", "请选择要读取的本地笔记文件。");
  if (files.length > MAX_LOCAL_IMPORT_FILES) throw new WeReadPortError("LOCAL_IMPORT", `一次最多读取 ${MAX_LOCAL_IMPORT_FILES} 个本地文本文件。`);
  const kinds = files.map(file => extensionKind(file.name));
  if (kinds.includes("unsupported")) throw new WeReadPortError("LOCAL_IMPORT", "只支持一个本工具导出 ZIP、一个规范化 JSON，或一组 Markdown/TXT 文件。");
  const distinct = new Set(kinds);
  if (distinct.size !== 1) throw new WeReadPortError("LOCAL_IMPORT", "请勿混合选择 ZIP、JSON 与文本文件；每次只导入一种来源。");
  const kind = kinds[0];
  if (["archive", "canonical"].includes(kind) && files.length !== 1) throw new WeReadPortError("LOCAL_IMPORT", `${kind === "archive" ? "ZIP" : "JSON"} 导入每次只能选择一个文件。`);

  const declaredTotal = files.reduce((sum, file) => sum + Math.max(0, Number(file.size) || 0), 0);
  if (kind === "archive") {
    if (declaredTotal > MAX_PREVIOUS_ARCHIVE_BYTES) throw new WeReadPortError("TOO_LARGE", "本地导出 ZIP 超过安全大小上限。");
  } else {
    if (declaredTotal > MAX_LOCAL_IMPORT_TOTAL_BYTES) throw new WeReadPortError("TOO_LARGE", "本地笔记文件总大小超过安全上限。");
    for (const file of files) if ((Number(file.size) || 0) > MAX_LOCAL_IMPORT_FILE_BYTES) throw new WeReadPortError("TOO_LARGE", `文件 ${file.name} 超过单文件安全上限。`);
  }
  if (!options.descriptorsOnly && declaredTotal === 0) throw new WeReadPortError("LOCAL_IMPORT", "所选文件为空，无法形成可导出的笔记。");
  return kind;
}

function extensionKind(name) {
  const extension = name.toLocaleLowerCase("en-US").split(".").pop() ?? "";
  if (extension === "zip") return "archive";
  if (extension === "json") return "canonical";
  if (TEXT_EXTENSIONS.has(extension)) return "text";
  return "unsupported";
}

async function importArchive(file) {
  const previousZip = file.bytes.slice();
  const previous = await loadPreviousExport(previousZip);
  const canonical = normalizeCanonicalSnapshot(previous.canonical, `本地导出包：${file.name}`);
  const snapshot = {
    ...canonical,
    source: canonical.source || "local-verified-export",
    books: canonical.books.map(book => withWarning(book, "此书来自用户主动上传且已完成完整性校验的旧导出包。")),
    failures: [],
  };
  return {
    kind: "archive",
    snapshot,
    summaries: snapshotToSummaries(snapshot),
    previousZip,
    info: { label: file.name, fileCount: 1, bookCount: snapshot.books.length, preservesProtectedRegions: true },
  };
}

async function importCanonicalJson(file) {
  let parsed;
  try { parsed = JSON.parse(decodeUtf8(file.bytes)); }
  catch (error) { throw new WeReadPortError("LOCAL_IMPORT", "规范化 JSON 不是有效的 UTF-8 JSON 文件。", { cause: error }); }
  const snapshot = normalizeCanonicalSnapshot(parsed, `本地规范化数据：${file.name}`);
  return {
    kind: "canonical",
    snapshot: { ...snapshot, source: "local-canonical-import", failures: [] },
    summaries: snapshotToSummaries(snapshot),
    previousZip: undefined,
    info: { label: file.name, fileCount: 1, bookCount: snapshot.books.length, preservesProtectedRegions: false },
  };
}

async function importTextFiles(files) {
  const books = [];
  const seenIds = new Set();
  for (const file of [...files].sort((a, b) => a.name.localeCompare(b.name, "zh-CN"))) {
    let text;
    try { text = decodeUtf8(file.bytes); }
    catch (error) { throw new WeReadPortError("LOCAL_IMPORT", `文件 ${file.name} 不是有效 UTF-8 文本。`, { cause: error }); }
    const parsed = parseTextDocument(text, file.name);
    if (!parsed.body) throw new WeReadPortError("LOCAL_IMPORT", `文件 ${file.name} 没有可读取的正文。`);
    const digest = await sha256Hex(file.bytes);
    let bookId = `local-${digest.slice(0, 24)}`;
    let suffix = 2;
    while (seenIds.has(bookId)) bookId = `local-${digest.slice(0, 20)}-${suffix++}`;
    seenIds.add(bookId);
    books.push(createLocalBook({ bookId, title: parsed.title, author: parsed.author, body: parsed.body, sourceName: file.name }));
  }
  const snapshot = {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: "local-text-import",
    sourceSkillVersion: LOCAL_IMPORT_CONTRACT_VERSION,
    exportProfile: "portable-commonmark",
    books,
    failures: [],
  };
  return {
    kind: "text",
    snapshot,
    summaries: snapshotToSummaries(snapshot),
    previousZip: undefined,
    info: { label: `${files.length} 个本地文本文件`, fileCount: files.length, bookCount: books.length, preservesProtectedRegions: false },
  };
}

function normalizeCanonicalSnapshot(value, originLabel) {
  if (!isPlainObject(value) || !Array.isArray(value.books)) throw new WeReadPortError("LOCAL_IMPORT", "规范化数据必须包含 books 数组。");
  if (value.books.length < 1 || value.books.length > MAX_BOOKS) throw new WeReadPortError("LOCAL_IMPORT", `规范化数据必须包含 1–${MAX_BOOKS} 本书。`);
  const books = [];
  const seen = new Set();
  for (let index = 0; index < value.books.length; index += 1) {
    const book = normalizeCanonicalBook(value.books[index], index, originLabel);
    if (seen.has(book.source.bookId)) throw new WeReadPortError("LOCAL_IMPORT", `规范化数据书籍标识重复：${book.source.bookId}`);
    seen.add(book.source.bookId);
    books.push(book);
  }
  books.sort((a, b) => a.metadata.title.localeCompare(b.metadata.title, "zh-CN") || a.source.bookId.localeCompare(b.source.bookId));
  return {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: safeString(value.source, "local-canonical-import", 128),
    sourceSkillVersion: safeString(value.sourceSkillVersion, LOCAL_IMPORT_CONTRACT_VERSION, 128),
    exportProfile: safeString(value.exportProfile, "portable-commonmark", 128),
    books,
    failures: [],
    readingStatistics: isPlainObject(value.readingStatistics) ? sanitizeJsonObject(value.readingStatistics, 0) : undefined,
  };
}

function normalizeCanonicalBook(value, index, originLabel) {
  if (!isPlainObject(value)) throw new WeReadPortError("LOCAL_IMPORT", `第 ${index + 1} 本书不是对象。`);
  const source = isPlainObject(value.source) ? value.source : {};
  const metadata = isPlainObject(value.metadata) ? value.metadata : {};
  const rawId = safeString(source.bookId ?? metadata.id, `local-book-${index + 1}`, 256);
  const title = safeString(metadata.title, `未命名笔记 ${index + 1}`, 512);
  const chapters = asLimitedArray(value.chapters, MAX_ITEMS_PER_BOOK, "章节").map((item, chapterIndex) => {
    const row = isPlainObject(item) ? item : {};
    return { uid: safeString(row.uid, `chapter-${chapterIndex + 1}`, 256), title: safeString(row.title, `章节 ${chapterIndex + 1}`, 512), level: safeInteger(row.level, 1), chapterIdx: safeInteger(row.chapterIdx, chapterIndex) };
  });
  if (!chapters.length) chapters.push({ uid: "local", title: "本地导入内容", level: 1, chapterIdx: 0 });
  const chapterFallback = chapters[0];
  const highlights = asLimitedArray(value.highlights, MAX_ITEMS_PER_BOOK, "划线").map((item, itemIndex) => normalizeHighlight(item, itemIndex, chapterFallback));
  const thoughts = asLimitedArray(value.thoughts, MAX_ITEMS_PER_BOOK, "想法").map((item, itemIndex) => normalizeThought(item, itemIndex, chapterFallback));
  return {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: { provider: safeString(source.provider, "local-import", 128), bookId: rawId, skillVersion: safeString(source.skillVersion, LOCAL_IMPORT_CONTRACT_VERSION, 128) },
    metadata: {
      id: safeString(metadata.id, rawId, 256),
      title,
      author: safeString(metadata.author, "", 512),
      translator: safeString(metadata.translator, "", 512),
      coverUrl: safeHttpsUrl(metadata.coverUrl),
      deepLink: safeSourceUrl(metadata.deepLink),
      intro: safeContent(metadata.intro, 200_000),
      category: safeString(metadata.category, "", 512),
      publisher: safeString(metadata.publisher, "", 512),
      publishTime: safeString(metadata.publishTime, "", 128),
      isbn: safeString(metadata.isbn, "", 128),
      wordCount: safeOptionalNumber(metadata.wordCount),
      rating: safeOptionalNumber(metadata.rating),
    },
    counts: { highlights: highlights.length, thoughtsAndReviews: thoughts.length, officialHighlightCount: highlights.length, officialReviewCount: thoughts.length, officialBookmarkCount: safeNonNegative(value?.counts?.officialBookmarkCount) },
    progress: {
      progress: safeOptionalNumber(value?.progress?.progress),
      readingTimeSeconds: safeOptionalNumber(value?.progress?.readingTimeSeconds),
      updateTime: safeOptionalNumber(value?.progress?.updateTime),
    },
    chapters,
    highlights,
    thoughts,
    sourceSnapshotAt: safeOptionalNumber(value.sourceSnapshotAt),
    sourceSnapshotAtIso: safeString(value.sourceSnapshotAtIso, "", 64) || undefined,
    warnings: [...new Set([
      ...asLimitedArray(value.warnings, 500, "提示").map(item => safeString(item, "", 2_000)).filter(Boolean),
      `此内容来自用户主动上传的${originLabel}；系统未向微信读书核验其来源。`,
    ])].sort((a, b) => a.localeCompare(b, "zh-CN")),
  };
}

function normalizeHighlight(value, index, chapter) {
  const row = isPlainObject(value) ? value : {};
  return {
    id: safeString(row.id, `highlight-${index + 1}`, 256),
    text: safeContent(row.text, MAX_TEXT_CHARS),
    chapterUid: safeString(row.chapterUid, chapter.uid, 256),
    chapterTitle: safeString(row.chapterTitle, chapter.title, 512),
    chapterIdx: safeInteger(row.chapterIdx, chapter.chapterIdx),
    range: safeString(row.range, "", 512),
    createdAt: safeOptionalNumber(row.createdAt),
    createdAtIso: safeString(row.createdAtIso, "", 64) || undefined,
  };
}

function normalizeThought(value, index, chapter) {
  const row = isPlainObject(value) ? value : {};
  return {
    id: safeString(row.id, `thought-${index + 1}`, 256),
    kind: ["highlight-thought", "chapter-comment", "book-review", "unclassified", "local-import"].includes(String(row.kind)) ? String(row.kind) : "unclassified",
    content: safeContent(row.content, MAX_TEXT_CHARS),
    abstract: safeContent(row.abstract, MAX_TEXT_CHARS),
    chapterUid: safeString(row.chapterUid, chapter.uid, 256),
    chapterTitle: safeString(row.chapterTitle, chapter.title, 512),
    chapterIdx: safeInteger(row.chapterIdx, chapter.chapterIdx),
    range: safeString(row.range, "", 512),
    createdAt: safeOptionalNumber(row.createdAt),
    createdAtIso: safeString(row.createdAtIso, "", 64) || undefined,
    star: safeOptionalNumber(row.star),
    isFinish: typeof row.isFinish === "boolean" ? row.isFinish : undefined,
  };
}

function createLocalBook({ bookId, title, author, body, sourceName }) {
  return {
    schemaVersion: CANONICAL_SCHEMA_VERSION,
    source: { provider: "local-file", bookId, skillVersion: LOCAL_IMPORT_CONTRACT_VERSION },
    metadata: { id: bookId, title, author, translator: "", coverUrl: "", deepLink: "", intro: "", category: "本地导入", publisher: "", publishTime: "", isbn: "", wordCount: undefined, rating: undefined },
    counts: { highlights: 0, thoughtsAndReviews: 1, officialHighlightCount: 0, officialReviewCount: 0, officialBookmarkCount: 0 },
    progress: { progress: undefined, readingTimeSeconds: undefined, updateTime: undefined },
    chapters: [{ uid: "local", title: "本地导入内容", level: 1, chapterIdx: 0 }],
    highlights: [],
    thoughts: [{ id: `${bookId}-note`, kind: "local-import", content: body, abstract: "", chapterUid: "local", chapterTitle: "本地导入内容", chapterIdx: 0, range: "", createdAt: undefined, createdAtIso: undefined }],
    sourceSnapshotAt: undefined,
    sourceSnapshotAtIso: undefined,
    warnings: [`此内容来自用户主动选择的本地文件“${safeString(sourceName, "未命名文件", 512)}”；系统未向微信读书核验其来源。`],
  };
}

function parseTextDocument(raw, filename) {
  let text = normalizeText(String(raw ?? "").replace(/^\uFEFF/, ""));
  let title = filename.replace(/\.(md|markdown|txt)$/i, "").trim() || "未命名笔记";
  let author = "";
  const frontmatter = text.match(/^---\n([\s\S]{0,20000}?)\n---(?:\n|$)/u);
  if (frontmatter) {
    for (const line of frontmatter[1].split("\n")) {
      const match = line.match(/^\s*(title|author)\s*:\s*(.+?)\s*$/iu);
      if (!match) continue;
      const value = unquoteSimple(match[2]);
      if (match[1].toLocaleLowerCase("en-US") === "title" && value) title = value;
      if (match[1].toLocaleLowerCase("en-US") === "author" && value) author = value;
    }
    text = normalizeText(text.slice(frontmatter[0].length));
  }
  const heading = text.match(/^#\s+(.+?)\s*$/mu);
  if (heading?.[1]) title = cleanReservedText(heading[1], 512);
  return { title: cleanReservedText(title, 512), author: cleanReservedText(author, 512), body: safeContent(text, MAX_TEXT_CHARS) };
}

function snapshotToSummaries(snapshot) {
  return snapshot.books.map(book => ({
    bookId: book.source.bookId,
    title: book.metadata.title,
    author: book.metadata.author,
    coverUrl: book.metadata.coverUrl || undefined,
    deepLink: book.metadata.deepLink || undefined,
    reviewCount: book.thoughts.length,
    highlightCount: book.highlights.length,
    bookmarkCount: Number(book.counts?.officialBookmarkCount ?? 0),
    totalNoteCount: book.thoughts.length + book.highlights.length + Number(book.counts?.officialBookmarkCount ?? 0),
    readingProgress: book.progress?.progress,
    sort: 0,
  }));
}

function withWarning(book, warning) { return { ...book, warnings: [...new Set([...(book.warnings ?? []), warning])].sort((a, b) => a.localeCompare(b, "zh-CN")) }; }
function asLimitedArray(value, max, label) { const list = Array.isArray(value) ? value : []; if (list.length > max) throw new WeReadPortError("LOCAL_IMPORT", `${label}数量超过安全上限 ${max}。`); return list; }
function safeString(value, fallback = "", max = 2_000) { const text = typeof value === "string" ? value : fallback; return cleanReservedText(text, max); }
function safeContent(value, max = MAX_TEXT_CHARS) {
  const text = normalizeText(typeof value === "string" ? value : "");
  if (text.length > max) throw new WeReadPortError("TOO_LARGE", `单条笔记正文超过安全上限 ${max} 个字符；为避免静默丢失，系统未截断并已停止本次导入。`);
  return cleanReservedText(text, max);
}
function cleanReservedText(value, max) { return normalizeText(String(value ?? "")).slice(0, max).replace(/<!--\s*weread-port:/giu, "&lt;!-- imported-weread-port:"); }
function safeInteger(value, fallback) { return Number.isInteger(value) ? value : fallback; }
function safeOptionalNumber(value) { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
function safeNonNegative(value) { const number = safeOptionalNumber(value); return number === undefined ? 0 : Math.max(0, Math.floor(number)); }
function safeHttpsUrl(value) { try { const url = new URL(typeof value === "string" ? value : ""); return url.protocol === "https:" ? url.toString() : ""; } catch { return ""; } }
function safeSourceUrl(value) { try { const url = new URL(typeof value === "string" ? value : ""); return ["https:", "weread:"].includes(url.protocol) ? String(value) : ""; } catch { return ""; } }
function unquoteSimple(value) { const text = String(value).trim(); try { if (/^(["']).*\1$/s.test(text)) return String(JSON.parse(text.replace(/^'/, '"').replace(/'$/, '"'))); } catch {} return text.replace(/^['"]|['"]$/g, ""); }
function sanitizeJsonObject(value, depth) { if (depth > 5) return {}; const out = {}; for (const [key, item] of Object.entries(value).slice(0, 200)) { if (typeof item === "string") out[safeString(key, "key", 128)] = safeString(item, "", 2_000); else if (typeof item === "number" && Number.isFinite(item)) out[safeString(key, "key", 128)] = item; else if (typeof item === "boolean" || item === null) out[safeString(key, "key", 128)] = item; else if (isPlainObject(item)) out[safeString(key, "key", 128)] = sanitizeJsonObject(item, depth + 1); } return out; }
