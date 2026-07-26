import { performance } from "node:perf_hooks";
import process from "node:process";
import { collectNotebookSummaries, collectSnapshot } from "../src/core/collector.js";
import { EXPORT_PROFILES } from "../src/core/constants.js";
import { createDemoCaller } from "../src/core/demo.js";
import { buildExport } from "../src/core/exporter.js";

const call = createDemoCaller();
const summaries = await collectNotebookSummaries({ key: "demo-only", call });
const seed = await collectSnapshot({
  key: "demo-only",
  summaries,
  exportProfile: EXPORT_PROFILES.PORTABLE,
  call,
  includeReadingStatistics: true,
});

const targetItems = Number(process.env.BENCHMARK_ITEMS ?? 10_000);
const maxMs = Number(process.env.BENCHMARK_MAX_MS ?? 30_000);
const sourceBook = seed.books[0];
const highlightsPerBook = 500;
const bookCount = Math.ceil(targetItems / highlightsPerBook);
const books = [];
let produced = 0;
for (let bookIndex = 0; bookIndex < bookCount; bookIndex += 1) {
  const remaining = targetItems - produced;
  const count = Math.min(highlightsPerBook, remaining);
  const highlights = Array.from({ length: count }, (_, index) => ({
    ...sourceBook.highlights[index % sourceBook.highlights.length],
    id: `bench-h-${bookIndex}-${index}`,
    text: `合成性能样本 ${bookIndex + 1}-${index + 1}：只用于验证本地导出，不含真实用户数据。`,
    createdAt: 1_700_000_000 + index,
    createdAtIso: new Date((1_700_000_000 + index) * 1000).toISOString(),
  }));
  books.push({
    ...structuredClone(sourceBook),
    source: { ...sourceBook.source, bookId: `bench-book-${String(bookIndex).padStart(4, "0")}` },
    metadata: { ...sourceBook.metadata, id: `bench-book-${bookIndex}`, title: `合成基准书籍 ${String(bookIndex + 1).padStart(4, "0")}` },
    counts: { ...sourceBook.counts, highlights: count, officialHighlightCount: count },
    highlights,
    thoughts: [],
  });
  produced += count;
}
const snapshot = { ...seed, books, failures: [], exportProfile: EXPORT_PROFILES.PORTABLE };
const start = performance.now();
const result = await buildExport(snapshot, { profile: EXPORT_PROFILES.PORTABLE, includeOfflineSearch: true });
const elapsedMs = performance.now() - start;
const rssMiB = process.memoryUsage().rss / (1024 * 1024);
const record = {
  targetItems,
  books: books.length,
  elapsedMs: Number(elapsedMs.toFixed(1)),
  archiveBytes: result.bytes.byteLength,
  rssMiB: Number(rssMiB.toFixed(1)),
  status: result.status,
  thresholdMs: maxMs,
};
console.log(JSON.stringify(record, null, 2));
if (result.status !== "COMPLETE" || result.manifest.bookCount !== books.length) process.exitCode = 1;
if (!Number.isFinite(elapsedMs) || elapsedMs > maxMs) {
  console.error(`Benchmark exceeded ${maxMs} ms.`);
  process.exitCode = 1;
}
