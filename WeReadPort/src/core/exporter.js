import { APP_NAME, APP_PRODUCT_ID, APP_VERSION, CANONICAL_SCHEMA_VERSION, EXPORT_CONTRACT_VERSION, EXPORT_PROFILES, EXPORT_STATUS, PROFILE_LABELS, SOURCE_SKILL_VERSION } from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { buildChatGPTPrompt, renderChatGPTContext, renderChatGPTGuide } from "./chatgpt-bridge.js";
import { renderOfflineSearch } from "./offline-search.js";
import { canonicalizeProtectedRegion, extractProtectedRegion } from "./protected-regions.js";
import { renderBookMarkdown } from "./render.js";
import { createDeterministicZip, readZipEntries } from "./zip.js";
import { assertSafeArchivePath, decodeUtf8, safeBookFilename, sha256Hex, stableStringify, utf8 } from "./util.js";

/**
 * Build a deterministic, self-verifying export. A previous export may be used to
 * preserve the protected user region. The complete source inventory is supplied
 * separately from the selected books so an intentionally unselected book is never
 * mistaken for an upstream deletion.
 *
 * @param {import('./model.js').CanonicalSnapshot} snapshot
 * @param {{profile:string,includeCover?:boolean,includeOfflineSearch?:boolean,previousZip?:Uint8Array|ArrayBuffer,knownSourceBookIds?:string[],sourceInventoryComplete?:boolean,retainUnselectedPrevious?:boolean,retainPreviousTombstones?:boolean}} options
 */
export async function buildExport(snapshot, options) {
  if (!Object.values(EXPORT_PROFILES).includes(options.profile)) throw new WeReadPortError("PROFILE", "未知导出格式。");
  if (!snapshot.books.length) throw new WeReadPortError("NO_EXPORTABLE_DATA", "没有可导出的书籍，未生成空压缩包。");

  const previous = options.previousZip ? await loadPreviousExport(options.previousZip) : emptyPreviousExport();
  const selectedIds = new Set(snapshot.books.map(book => book.source.bookId));
  const knownIds = new Set((options.knownSourceBookIds ?? snapshot.books.map(book => book.source.bookId)).map(String));
  const inventoryComplete = options.sourceInventoryComplete === true;
  const retainedBooks = [];
  const retainUnselectedPrevious = options.retainUnselectedPrevious !== false;
  if (retainUnselectedPrevious) for (const [sourceId, prior] of previous.byBookId) {
    if (selectedIds.has(sourceId)) continue;
    if (inventoryComplete && !knownIds.has(sourceId)) continue;
    const canonical = previous.canonicalBooksById.get(sourceId);
    if (!canonical) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出缺少已登记书籍的规范化数据：${sourceId}`);
    retainedBooks.push(markRetainedBook(canonical));
  }
  const effectiveSnapshot = {
    ...snapshot,
    books: [...snapshot.books, ...retainedBooks].sort((a, b) => a.metadata.title.localeCompare(b.metadata.title, "zh-CN") || a.source.bookId.localeCompare(b.source.bookId)),
  };

  const canonicalText = stableStringify(effectiveSnapshot);
  const canonicalHash = await sha256Hex(canonicalText);
  const chatgptFilename = `给ChatGPT的阅读笔记-${canonicalHash.slice(0, 12)}.md`;
  let chatgptContextBytes;
  let chatgptContextSha256;
  let chatgptPrompt;
  let chatgptHandoffIssue;
  try {
    const chatgptContext = renderChatGPTContext(effectiveSnapshot, { profile: options.profile, canonicalSha256: canonicalHash });
    chatgptContextBytes = utf8(chatgptContext);
    chatgptContextSha256 = await sha256Hex(chatgptContextBytes);
    chatgptPrompt = buildChatGPTPrompt(chatgptFilename);
  } catch (error) {
    if (["CHATGPT_CONTEXT_TOO_LARGE", "CHATGPT_HANDOFF_SECRET"].includes(error?.code)) chatgptHandoffIssue = { code: error.code, message: error.message };
    else throw error;
  }
  /** @type {Array<{path:string,data:string|Uint8Array}>} */
  const entries = [];
  const usedPaths = new Set();
  const manifestBooks = [];
  for (const book of effectiveSnapshot.books) {
    const prior = previous.byBookId.get(book.source.bookId);
    const preferredPath = prior?.path?.startsWith("books/") ? assertSafeArchivePath(prior.path) : `books/${safeBookFilename(book.metadata.title, book.source.bookId)}`;
    const path = reservePath(preferredPath, usedPaths, `books/${safeBookFilename(book.metadata.title, book.source.bookId)}`);
    const generatedMarkdown = renderBookMarkdown(book, { profile: options.profile, includeCover: options.includeCover });
    const markdown = prior ? renderBookMarkdown(book, { profile: options.profile, includeCover: options.includeCover, preservedRegion: prior.region }) : generatedMarkdown;
    const bytes = utf8(markdown);
    const generatedBytes = utf8(generatedMarkdown);
    entries.push({ path, data: bytes });
    manifestBooks.push({
      sourceId: book.source.bookId,
      title: book.metadata.title,
      author: book.metadata.author,
      path,
      sha256: await sha256Hex(bytes),
      generatedSha256: await sha256Hex(generatedBytes),
      retainedFromPreviousExport: !selectedIds.has(book.source.bookId),
      counts: book.counts,
      warnings: book.warnings,
    });
  }
  manifestBooks.sort((a, b) => a.sourceId.localeCompare(b.sourceId));

  const tombstones = [];
  const sourceSnapshotAt = Math.max(0, ...effectiveSnapshot.books.map(book => book.sourceSnapshotAt ?? 0));
  for (const [sourceId, prior] of previous.byBookId) {
    if (selectedIds.has(sourceId) || !inventoryComplete || knownIds.has(sourceId)) continue;
    const path = reservePath(`tombstones/books/${safeBookFilename(prior.title || "deleted-book", sourceId)}`, usedPaths);
    entries.push({ path, data: prior.bytes });
    tombstones.push({
      sourceId,
      title: prior.title,
      author: prior.author,
      originalPath: prior.path,
      path,
      sha256: await sha256Hex(prior.bytes),
      detectedAtSourceSnapshot: sourceSnapshotAt || null,
      reason: "not_present_in_complete_source_inventory",
    });
  }
  if (options.retainPreviousTombstones !== false) for (const [sourceId, prior] of previous.tombstonesByBookId) {
    if (selectedIds.has(sourceId)) continue;
    const preferred = prior.path?.startsWith("tombstones/") ? prior.path : `tombstones/books/${safeBookFilename(prior.title || "deleted-book", sourceId)}`;
    const path = reservePath(preferred, usedPaths, `tombstones/books/${safeBookFilename(prior.title || "deleted-book", sourceId)}`);
    entries.push({ path, data: prior.bytes });
    tombstones.push({ ...prior.record, path, sha256: await sha256Hex(prior.bytes) });
  }
  tombstones.sort((a, b) => a.sourceId.localeCompare(b.sourceId));

  const indexMarkdown = renderBookIndex(effectiveSnapshot, manifestBooks, tombstones.length);
  entries.push({ path: "BOOKS_INDEX.md", data: indexMarkdown });
  entries.push({ path: "data/canonical-reading-model.json", data: canonicalText });
  if (chatgptContextBytes) entries.push({ path: "chatgpt/阅读笔记上下文.md", data: chatgptContextBytes });
  entries.push({ path: "CHATGPT_使用说明.md", data: renderChatGPTGuide(chatgptFilename, chatgptHandoffIssue) });
  if (effectiveSnapshot.readingStatistics) entries.push({ path: "READING_STATISTICS.md", data: renderReadingStatistics(effectiveSnapshot.readingStatistics) });
  if (options.includeOfflineSearch !== false) entries.push({ path: "offline/index.html", data: renderOfflineSearch(effectiveSnapshot, manifestBooks) });
  if (tombstones.length) entries.push({ path: "DELETED_UPSTREAM.md", data: renderDeletedReport(tombstones) });

  const status = effectiveSnapshot.failures.length || chatgptHandoffIssue ? EXPORT_STATUS.PARTIAL : EXPORT_STATUS.COMPLETE;
  entries.push(
    { path: "README.md", data: renderExportReadme(options.profile, status) },
    { path: "EXPORT_REPORT.md", data: renderExportReport(effectiveSnapshot, status, canonicalHash, sourceSnapshotAt, tombstones, retainedBooks.length, chatgptHandoffIssue) },
  );

  const fileRecords = await createFileRecords(entries);
  const manifest = {
    product: APP_PRODUCT_ID,
    productName: APP_NAME,
    appVersion: APP_VERSION,
    exportContractVersion: EXPORT_CONTRACT_VERSION,
    canonicalSchemaVersion: CANONICAL_SCHEMA_VERSION,
    sourceSkillVersion: effectiveSnapshot.sourceSkillVersion || SOURCE_SKILL_VERSION,
    source: effectiveSnapshot.source,
    profile: options.profile,
    profileLabel: PROFILE_LABELS[options.profile],
    status,
    statusLabel: exportStatusLabel(status),
    sourceSnapshotAt: sourceSnapshotAt || null,
    canonicalSha256: canonicalHash,
    bookCount: manifestBooks.length,
    updatedBookCount: snapshot.books.length,
    retainedBookCount: retainedBooks.length,
    tombstoneCount: tombstones.length,
    sourceFailureCount: effectiveSnapshot.failures.length,
    artifactFailureCount: chatgptHandoffIssue ? 1 : 0,
    failureCount: effectiveSnapshot.failures.length + (chatgptHandoffIssue ? 1 : 0),
    sourceInventoryComplete: inventoryComplete,
    chatgptHandoff: chatgptContextBytes ? {
      status: "READY",
      contextPath: "chatgpt/阅读笔记上下文.md",
      contextFilename: chatgptFilename,
      contextSha256: chatgptContextSha256,
      transport: "manual-user-confirmed-upload",
    } : {
      status: "NOT_GENERATED",
      code: chatgptHandoffIssue.code,
      message: chatgptHandoffIssue.message,
      transport: "manual-user-confirmed-upload",
    },
    books: manifestBooks,
    tombstones,
    files: fileRecords,
  };
  entries.push({ path: "manifest.json", data: stableStringify(manifest) });

  const checksumRecords = [];
  for (const entry of [...entries].sort((a, b) => a.path.localeCompare(b.path))) {
    checksumRecords.push(`${await sha256Hex(entryBytes(entry))}  ${entry.path}`);
  }
  entries.push({ path: "CHECKSUMS.sha256", data: `${checksumRecords.join("\n")}\n` });
  const zip = createDeterministicZip(entries);
  return {
    bytes: zip,
    filename: `微信读书笔记迁移-${profileFilename(options.profile)}-${canonicalHash.slice(0, 12)}.zip`,
    manifest,
    status,
    chatgpt: chatgptContextBytes ? {
      bytes: chatgptContextBytes,
      filename: chatgptFilename,
      sha256: chatgptContextSha256,
      prompt: chatgptPrompt,
    } : undefined,
  };
}

/** 在读取用户补充内容前，完整校验上一次“微信读书笔记迁移”导出包。@param {Uint8Array|ArrayBuffer} input */
export async function loadPreviousExport(input) {
  const entries = await readZipEntries(input);
  const manifestBytes = entries.get("manifest.json");
  const checksumBytes = entries.get("CHECKSUMS.sha256");
  if (!manifestBytes || !checksumBytes) throw new WeReadPortError("PREVIOUS_EXPORT", "旧压缩包缺少文件清单或校验值清单，不能安全合并。");

  let manifest;
  try { manifest = JSON.parse(decodeUtf8(manifestBytes)); }
  catch (error) { throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的 manifest.json 无法解析。", { cause: error }); }
  if (!manifest || ![APP_PRODUCT_ID, APP_NAME].includes(manifest.product) || !Array.isArray(manifest.books) || !Array.isArray(manifest.files)) {
    throw new WeReadPortError("PREVIOUS_EXPORT", "旧压缩包不是受支持的微信读书笔记迁移导出。");
  }
  if (manifest.exportContractVersion !== EXPORT_CONTRACT_VERSION || manifest.canonicalSchemaVersion !== CANONICAL_SCHEMA_VERSION) {
    throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出合同或规范化数据结构版本不兼容；请先用对应版本无损升级。");
  }

  const bookRecordsByPath = new Map();
  const seenSourceIds = new Set();
  for (const record of manifest.books) {
    if (!record || typeof record.sourceId !== "string" || typeof record.path !== "string") throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出包含无效书籍映射。");
    if (seenSourceIds.has(record.sourceId)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出书籍标识重复：${record.sourceId}`);
    const path = assertSafeArchivePath(record.path);
    if (!path.startsWith("books/") || bookRecordsByPath.has(path)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出书籍路径无效或重复：${path}`);
    seenSourceIds.add(record.sourceId);
    bookRecordsByPath.set(path, record);
  }

  await verifyPreviousIntegrity(entries, manifest, checksumBytes, bookRecordsByPath);
  const canonicalBytes = entries.get("data/canonical-reading-model.json");
  if (!canonicalBytes) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出缺少规范化阅读数据。");
  let canonical;
  try { canonical = JSON.parse(decodeUtf8(canonicalBytes)); }
  catch (error) { throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的规范化阅读数据无法解析。", { cause: error }); }
  if (!canonical || !Array.isArray(canonical.books)) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的规范化阅读数据结构无效。");
  const canonicalBooksById = new Map();
  for (const book of canonical.books) {
    const sourceId = book?.source?.bookId;
    if (typeof sourceId !== "string" || canonicalBooksById.has(sourceId)) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的规范化书籍标识缺失或重复。");
    canonicalBooksById.set(sourceId, book);
  }

  const byBookId = new Map();
  for (const record of manifest.books) {
    const path = assertSafeArchivePath(record.path);
    const bytes = entries.get(path);
    if (!bytes) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出缺少已登记文件：${path}`);
    if (!canonicalBooksById.has(record.sourceId)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出 规范化数据缺少 bookId：${record.sourceId}`);
    const markdown = decodeUtf8(bytes);
    byBookId.set(record.sourceId, {
      sourceId: record.sourceId,
      title: typeof record.title === "string" ? record.title : "",
      author: typeof record.author === "string" ? record.author : "",
      path,
      bytes,
      region: extractProtectedRegion(markdown),
      generatedSha256: typeof record.generatedSha256 === "string" ? record.generatedSha256 : undefined,
    });
  }

  const tombstonesByBookId = new Map();
  for (const record of Array.isArray(manifest.tombstones) ? manifest.tombstones : []) {
    if (!record || typeof record.sourceId !== "string" || typeof record.path !== "string") throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出包含无效的非破坏归档记录。");
    const path = assertSafeArchivePath(record.path);
    if (!path.startsWith("tombstones/") || tombstonesByBookId.has(record.sourceId)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出的非破坏归档路径或标识无效：${path}`);
    const bytes = entries.get(path);
    if (!bytes) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出缺少非破坏归档文件：${path}`);
    tombstonesByBookId.set(record.sourceId, { path, bytes, title: String(record.title ?? ""), record });
  }
  return { byBookId, canonicalBooksById, tombstonesByBookId, manifest, canonical };
}

function emptyPreviousExport() {
  return { byBookId: new Map(), canonicalBooksById: new Map(), tombstonesByBookId: new Map(), manifest: undefined, canonical: undefined };
}

/** @param {Map<string,Uint8Array>} entries @param {Record<string,any>} manifest @param {Uint8Array} checksumBytes @param {Map<string,Record<string,any>>} bookRecordsByPath */
async function verifyPreviousIntegrity(entries, manifest, checksumBytes, bookRecordsByPath) {
  const checksums = parseChecksums(checksumBytes);
  const expectedChecksumPaths = new Set([...entries.keys()].filter(path => path !== "CHECKSUMS.sha256"));
  if (!sameSet(new Set(checksums.keys()), expectedChecksumPaths)) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的校验值清单与 压缩包内容不一致。");

  const protectedValidity = new Map();
  const protectedOnlyValid = async (path, bytes) => {
    if (protectedValidity.has(path)) return protectedValidity.get(path);
    const record = bookRecordsByPath.get(path);
    let valid = false;
    if (record && typeof record.generatedSha256 === "string" && /^[0-9a-f]{64}$/i.test(record.generatedSha256)) {
      try { valid = await sha256Hex(utf8(canonicalizeProtectedRegion(decodeUtf8(bytes)))) === record.generatedSha256.toLowerCase(); }
      catch { valid = false; }
    }
    protectedValidity.set(path, valid);
    return valid;
  };

  for (const [path, expected] of checksums) {
    const bytes = entries.get(path);
    if (!bytes) throw new WeReadPortError("PREVIOUS_EXPORT", `校验值清单登记文件缺失：${path}`);
    const actual = await sha256Hex(bytes);
    if (actual !== expected && !(await protectedOnlyValid(path, bytes))) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出完整性校验失败：${path}`);
  }

  const expectedFilePaths = new Set([...entries.keys()].filter(path => !["manifest.json", "CHECKSUMS.sha256"].includes(path)));
  const manifestFilePaths = new Set();
  for (const record of manifest.files) {
    if (!record || typeof record.path !== "string") throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出 manifest.files 记录无效。");
    const path = assertSafeArchivePath(record.path);
    if (manifestFilePaths.has(path)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出 manifest.files 路径重复：${path}`);
    manifestFilePaths.add(path);
    const bytes = entries.get(path);
    if (!bytes) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出 manifest.files 指向缺失文件：${path}`);
    const actual = await sha256Hex(bytes);
    const exact = actual === record.sha256 && bytes.byteLength === record.bytes;
    if (!exact && !(await protectedOnlyValid(path, bytes))) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出 manifest 文件记录不匹配：${path}`);
  }
  if (!sameSet(manifestFilePaths, expectedFilePaths)) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的 manifest.files 与压缩包内容不一致。");

  for (const [path, record] of bookRecordsByPath) {
    const bytes = entries.get(path);
    if (!bytes) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出缺少书籍文件：${path}`);
    const actual = await sha256Hex(bytes);
    if (typeof record.generatedSha256 === "string") {
      if (!(await protectedOnlyValid(path, bytes))) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出的生成内容在个人补充区之外发生变化：${path}`);
      if (actual !== record.sha256 && !(await protectedOnlyValid(path, bytes))) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出书籍摘要不匹配：${path}`);
    } else if (actual !== record.sha256) {
      throw new WeReadPortError("PREVIOUS_EXPORT", `旧版导出缺少受保护区域完整性元数据，且书籍文件已变化：${path}`);
    }
  }

  const canonicalBytes = entries.get("data/canonical-reading-model.json");
  if (!canonicalBytes || await sha256Hex(canonicalBytes) !== manifest.canonicalSha256) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的规范化数据 SHA-256 不匹配。");
}

/** @param {Uint8Array} bytes */
function parseChecksums(bytes) {
  const map = new Map();
  const text = decodeUtf8(bytes);
  for (const line of text.split("\n")) {
    if (!line) continue;
    const match = line.match(/^([0-9a-f]{64})  (.+)$/i);
    if (!match) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的校验值清单格式无效。");
    const path = assertSafeArchivePath(match[2]);
    if (path === "CHECKSUMS.sha256" || map.has(path)) throw new WeReadPortError("PREVIOUS_EXPORT", `旧导出的校验值路径无效或重复：${path}`);
    map.set(path, match[1].toLowerCase());
  }
  if (!map.size) throw new WeReadPortError("PREVIOUS_EXPORT", "旧导出的校验值清单为空。");
  return map;
}

/** @param {Set<string>} left @param {Set<string>} right */
function sameSet(left, right) { return left.size === right.size && [...left].every(value => right.has(value)); }

/** @param {import('./model.js').CanonicalBook} book */
function markRetainedBook(book) {
  const warning = "本书本次未被选择，沿用上次已校验导出快照；选择本书后可刷新。";
  return { ...book, warnings: [...new Set([...(Array.isArray(book.warnings) ? book.warnings : []), warning])].sort((a, b) => a.localeCompare(b, "zh-CN")) };
}

/** @param {string} preferred @param {Set<string>} used @param {string} [fallback] */
function reservePath(preferred, used, fallback = preferred) {
  let path = assertSafeArchivePath(preferred);
  if (!used.has(path)) { used.add(path); return path; }
  path = assertSafeArchivePath(fallback);
  if (!used.has(path)) { used.add(path); return path; }
  const dot = path.lastIndexOf(".");
  const stem = dot > path.lastIndexOf("/") ? path.slice(0, dot) : path;
  const extension = dot > path.lastIndexOf("/") ? path.slice(dot) : "";
  for (let index = 2; index <= 10_000; index += 1) {
    const candidate = `${stem}-${index}${extension}`;
    if (!used.has(candidate)) { used.add(candidate); return candidate; }
  }
  throw new WeReadPortError("ARCHIVE", `无法为导出文件分配唯一安全路径：${path}`);
}

/** @param {Array<{path:string,data:string|Uint8Array}>} entries */
async function createFileRecords(entries) {
  const records = [];
  for (const entry of [...entries].sort((a, b) => a.path.localeCompare(b.path))) {
    const bytes = entryBytes(entry);
    records.push({ path: entry.path, bytes: bytes.byteLength, sha256: await sha256Hex(bytes) });
  }
  return records;
}

/** @param {{data:string|Uint8Array}} entry */
function entryBytes(entry) { return typeof entry.data === "string" ? utf8(entry.data) : entry.data; }

/** @param {import('./model.js').CanonicalSnapshot} snapshot @param {Array<{sourceId:string,title:string,author:string,path:string}>} books @param {number} tombstoneCount */
function renderBookIndex(snapshot, books, tombstoneCount) {
  const lines = ["# 微信读书笔记索引", "", `共 ${books.length} 本书。`];
  if (snapshot.failures.length) lines.push(`有 ${snapshot.failures.length} 项失败，详见 \`EXPORT_REPORT.md\`。`);
  if (tombstoneCount) lines.push(`有 ${tombstoneCount} 本旧书未出现在完整上游清单中，已非破坏性归档，详见 \`DELETED_UPSTREAM.md\`。`);
  lines.push("");
  for (const book of [...books].sort((a, b) => a.title.localeCompare(b.title, "zh-CN") || a.sourceId.localeCompare(b.sourceId))) lines.push(`- [${escapeLinkText(book.title)}](${encodePath(book.path)})${book.author ? ` — ${escapeLinkText(book.author)}` : ""}`);
  return `${lines.join("\n")}\n`;
}

/** @param {string} profile @param {string} status */
function renderExportReadme(profile, status) {
  return `# 微信读书笔记迁移导出包

状态：**${exportStatusLabel(status)}**  
格式：**${PROFILE_LABELS[profile]}**

## 打开方式

1. 从 \`BOOKS_INDEX.md\`（书籍索引）进入单本书笔记。
2. 双击 \`offline/index.html\`（离线搜索）即可搜索当前书籍的划线与想法。
3. \`data/canonical-reading-model.json\` 是结构化、可迁移的规范化阅读模型。
4. \`CHECKSUMS.sha256\` 与 \`manifest.json\` 用于校验包内文件完整性。
5. 再次导出时上传本压缩包，可原样保留每本书的“我的永久补充”区域。
6. 完整上游清单中消失的旧书不会被静默删除，而会进入 \`tombstones/\`（非破坏性归档）并记录在 \`DELETED_UPSTREAM.md\`。

## 兼容性与安全

- 所有文本均采用 UTF-8、LF 换行和 NFC 规范化。
- 文件名包含稳定的书籍标识哈希，避免同名书互相覆盖。
- 压缩包使用确定性不压缩存储模式，便于校验与版本管理。
- 仅“我的永久补充”标记区允许用户编辑后继续合并；生成内容的其他变化会被拒绝。
- 书签仅有计数；微信读书官方当前接口不返回书签正文。

本工具与腾讯、微信读书无隶属、授权或背书关系。数据仅来自用户本人授权调用的官方接口，或用户主动选择的本地文件。
`;
}

/** @param {import('./model.js').CanonicalSnapshot} snapshot @param {string} status @param {string} canonicalHash @param {number} sourceSnapshotAt @param {Array<Record<string,any>>} tombstones @param {number} retainedCount */
function renderExportReport(snapshot, status, canonicalHash, sourceSnapshotAt, tombstones, retainedCount, chatgptHandoffIssue) {
  const lines = ["# 导出报告", "", `- 状态：**${exportStatusLabel(status)}**`, `- 当前读取书籍：${snapshot.books.length - retainedCount}`, `- 沿用上次快照：${retainedCount}`, `- 非破坏归档记录：${tombstones.length}`, `- 失败项：${snapshot.failures.length + (chatgptHandoffIssue ? 1 : 0)}`, `- 规范化数据 SHA-256：\`${canonicalHash}\``, `- 上游技能版本：\`${snapshot.sourceSkillVersion}\``, `- 数据快照时间：${sourceSnapshotAt ? new Date(sourceSnapshotAt * 1000).toISOString() : "上游未提供"}`, ""];
  if (snapshot.failures.length || chatgptHandoffIssue) {
    lines.push("## 未完成项", "");
    for (const failure of snapshot.failures) lines.push(`- \`${failure.code}\`${failure.bookId ? `（书籍标识：\`${failure.bookId}\`）` : ""}：${failure.message}`);
    if (chatgptHandoffIssue) lines.push(`- \`${chatgptHandoffIssue.code}\`：${chatgptHandoffIssue.message}；完整迁移压缩包中的其他制品仍已保留。`);
    lines.push("");
  }
  if (tombstones.length) lines.push("## 上游消失项", "", "旧文件已保留在 `tombstones/`（非破坏性归档）；系统没有静默删除任何旧标记文本。详见 `DELETED_UPSTREAM.md`（上游消失记录）。", "");
  lines.push("## 判定规则", "", "只要存在单书失败、阅读统计失败或其他可见缺口，状态即为“部分完成”；系统不会把失败伪装成完整成功，也不会在所有书均失败时生成空压缩包。非破坏归档记录不等同于失败。", "");
  return `${lines.join("\n")}\n`;
}

/** @param {Array<Record<string,any>>} tombstones */
function renderDeletedReport(tombstones) {
  const lines = ["# 上游消失书籍的非破坏性归档", "", "以下书籍未出现在本次完整的微信读书笔记本清单中。旧标记文本被原样归档，不代表本工具已经确认用户主动删除；重新出现并被选择导出后会恢复为当前书籍。", ""];
  for (const record of tombstones) lines.push(`- [${escapeLinkText(record.title || record.sourceId)}](${encodePath(record.path)})${record.author ? ` — ${escapeLinkText(record.author)}` : ""} · bookId \`${record.sourceId}\``);
  return `${lines.join("\n")}\n`;
}

/** @param {Record<string,unknown>} statistics */
function renderReadingStatistics(statistics) {
  const seconds = typeof statistics.totalReadingTimeSeconds === "number" ? statistics.totalReadingTimeSeconds : undefined;
  const duration = seconds === undefined ? "未提供" : formatReadingDuration(seconds);
  const days = typeof statistics.totalReadingDays === "number" ? String(statistics.totalReadingDays) : "未提供";
  const finished = typeof statistics.totalFinishedBooks === "number" ? String(statistics.totalFinishedBooks) : "未提供";
  return `# 阅读统计\n\n- 统计范围：${readingModeLabel(String(statistics.mode ?? "overall"))}\n- 总阅读时长：${duration}\n- 总阅读天数：${days}\n- 读完书籍：${finished}\n\n数据来自微信读书官方智能接口网关；字段缺失时不会推测。\n`;
}

function exportStatusLabel(status) { return status === EXPORT_STATUS.COMPLETE ? "完整完成" : status === EXPORT_STATUS.PARTIAL ? "部分完成" : "未完成"; }
function profileFilename(profile) { return ({ [EXPORT_PROFILES.PORTABLE]: "便携纯文本", [EXPORT_PROFILES.GFM]: "代码仓库", [EXPORT_PROFILES.OBSIDIAN]: "双链笔记", [EXPORT_PROFILES.NOTION]: "协作笔记" }[profile] ?? "通用"); }
function readingModeLabel(mode) { return ({ weekly: "本周", monthly: "本月", annually: "本年", overall: "全部时间" }[mode] ?? "上游自定义范围"); }

/** @param {number} seconds */
function formatReadingDuration(seconds) { const total = Math.max(0, Math.floor(seconds)); const hours = Math.floor(total / 3600); const minutes = Math.floor((total % 3600) / 60); return `${hours}小时${minutes}分钟`; }
/** @param {string} value */
function escapeLinkText(value) { return value.replace(/([\\\[\]])/g, "\\$1").replace(/\n/g, " "); }
/** @param {string} path */
function encodePath(path) { return path.split("/").map(segment => encodeURIComponent(segment)).join("/"); }
