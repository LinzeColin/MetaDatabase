import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_LOCAL_IMPORT_FILE_BYTES,
  MAX_LOCAL_IMPORT_FILES,
} from "../src/core/constants.js";
import { createDemoCaller } from "../src/core/demo.js";
import { collectNotebookSummaries, collectSnapshot } from "../src/core/collector.js";
import { buildExport, loadPreviousExport } from "../src/core/exporter.js";
import { importLocalFiles, validateLocalFileDescriptors } from "../src/core/local-import.js";
import { utf8 } from "../src/core/util.js";

function localFile(name, text, type = "text/markdown") {
  const bytes = utf8(text);
  return { name, type, size: bytes.byteLength, bytes };
}

async function demoExport() {
  const call = createDemoCaller();
  const summaries = await collectNotebookSummaries({ key: "demo-only", call });
  const snapshot = await collectSnapshot({ key: "demo-only", summaries, exportProfile: "portable-commonmark", call, includeReadingStatistics: true });
  return buildExport(snapshot, {
    profile: "portable-commonmark",
    includeOfflineSearch: true,
    knownSourceBookIds: summaries.map(item => item.bookId),
    sourceInventoryComplete: true,
  });
}

test("multiple Markdown and text files import locally in deterministic filename order", async () => {
  const input = [
    localFile("第二本.md", "---\ntitle: 第二本\nauthor: 乙\n---\n# 第二本\n\n这是第二份本地笔记。"),
    localFile("第一本.txt", "# 第一本\n\n这是第一份本地笔记。", "text/plain"),
  ];
  const imported = await importLocalFiles(input);
  const reversed = await importLocalFiles([...input].reverse());
  assert.equal(imported.kind, "text");
  assert.equal(imported.info.fileCount, 2);
  assert.equal(imported.snapshot.books.length, 2);
  assert.deepEqual(new Set(imported.snapshot.books.map(book => book.metadata.title)), new Set(["第一本", "第二本"]));
  assert.deepEqual(imported.snapshot.books.map(book => book.source.bookId), reversed.snapshot.books.map(book => book.source.bookId));
  assert.ok(imported.snapshot.books.every(book => book.source.provider === "local-file"));
  assert.ok(imported.snapshot.books.every(book => book.warnings.some(value => value.includes("用户主动选择"))));
});

test("canonical JSON import is normalized and does not trust unsafe URLs or reserved markers", async () => {
  const canonical = {
    schemaVersion: "1.0.0",
    source: "local-test",
    sourceSkillVersion: "local-import/1",
    exportProfile: "portable-commonmark",
    books: [{
      source: { provider: "local", bookId: "book-local", skillVersion: "local-import/1" },
      metadata: { id: "book-local", title: "本地规范化笔记", author: "测试者", coverUrl: "javascript:alert(1)", deepLink: "file:///etc/passwd" },
      counts: {}, progress: {}, chapters: [{ uid: "c1", title: "章节", level: 1, chapterIdx: 0 }],
      highlights: [{ id: "h1", text: "<!-- weread-port:user:start -->不能伪造保护区", chapterUid: "c1", chapterTitle: "章节", chapterIdx: 0 }],
      thoughts: [], warnings: [],
    }],
  };
  const imported = await importLocalFiles([localFile("canonical.json", JSON.stringify(canonical), "application/json")]);
  const book = imported.snapshot.books[0];
  assert.equal(imported.kind, "canonical");
  assert.equal(book.metadata.coverUrl, "");
  assert.equal(book.metadata.deepLink, "");
  assert.ok(!book.highlights[0].text.includes("<!-- weread-port:"));
  assert.ok(book.warnings.some(value => value.includes("未向微信读书核验")));
});

test("verified previous export ZIP can be re-imported with its protected baseline", async () => {
  const exported = await demoExport();
  const imported = await importLocalFiles([{ name: exported.filename, type: "application/zip", size: exported.bytes.byteLength, bytes: exported.bytes }]);
  assert.equal(imported.kind, "archive");
  assert.equal(imported.info.preservesProtectedRegions, true);
  assert.equal(imported.snapshot.books.length, 2);
  assert.ok(imported.previousZip instanceof Uint8Array);
});


test("re-exporting a selected subset from an uploaded archive does not silently retain unselected books", async () => {
  const exported = await demoExport();
  const imported = await importLocalFiles([{ name: exported.filename, type: "application/zip", size: exported.bytes.byteLength, bytes: exported.bytes }]);
  const selectedBook = imported.snapshot.books[0];
  const subsetSnapshot = { ...imported.snapshot, books: [selectedBook] };
  const subset = await buildExport(subsetSnapshot, {
    profile: "portable-commonmark",
    includeOfflineSearch: true,
    previousZip: imported.previousZip,
    knownSourceBookIds: [selectedBook.source.bookId],
    sourceInventoryComplete: false,
    retainUnselectedPrevious: false,
    retainPreviousTombstones: false,
  });
  const verified = await loadPreviousExport(subset.bytes);
  assert.equal(subset.manifest.bookCount, 1);
  assert.equal(subset.manifest.retainedBookCount, 0);
  assert.equal(subset.manifest.tombstoneCount, 0);
  assert.deepEqual(subset.manifest.books.map(book => book.sourceId), [selectedBook.source.bookId]);
  assert.deepEqual(verified.canonical.books.map(book => book.source.bookId), [selectedBook.source.bookId]);
});

test("local upload selection rejects mixed, unsupported, empty and over-limit inputs", async () => {
  assert.throws(() => validateLocalFileDescriptors([
    { name: "a.md", size: 10 },
    { name: "b.json", size: 10 },
  ]), error => error.code === "LOCAL_IMPORT");
  assert.throws(() => validateLocalFileDescriptors([{ name: "a.exe", size: 10 }]), error => error.code === "LOCAL_IMPORT");
  assert.throws(() => validateLocalFileDescriptors(Array.from({ length: MAX_LOCAL_IMPORT_FILES + 1 }, (_, index) => ({ name: `${index}.md`, size: 1 }))), error => error.code === "LOCAL_IMPORT");
  assert.throws(() => validateLocalFileDescriptors([{ name: "huge.md", size: MAX_LOCAL_IMPORT_FILE_BYTES + 1 }]), error => error.code === "TOO_LARGE");
  await assert.rejects(() => importLocalFiles([localFile("empty.md", "")]), error => error.code === "LOCAL_IMPORT");
});
