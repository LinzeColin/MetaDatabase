import { performance } from "node:perf_hooks";
import { testPlatform } from "../tests/service/helpers.mjs";

const targetItems = Number(process.env.PLATFORM_BENCHMARK_ITEMS || 10_000);
const maxMs = Number(process.env.PLATFORM_BENCHMARK_MAX_MS || 30_000);
const platform = testPlatform();
try {
  const account = await platform.service.registerPassword({ email: "benchmark@example.test", password: "Benchmark-Password-2026", displayName: "容量验证" });
  const started = performance.now();
  for (let index = 0; index < targetItems; index += 1) {
    await platform.service.saveDocument(account.account.id, {
      source: "benchmark", externalId: `sample-${index}`, title: `合成笔记 ${index + 1}`,
      category: `主题-${index % 12}`, content: `这是第 ${index + 1} 条合成阅读笔记，只用于账户隔离、加密存储和容量验证。`,
    });
  }
  const elapsedMs = performance.now() - started;
  const rssMiB = process.memoryUsage().rss / 1024 / 1024;
  const pull = await platform.service.syncPull(account.account.id, 0, 500);
  const record = { targetItems, storedNotes: platform.store.counts().notes, firstSyncBatch: pull.events.length, elapsedMs: Number(elapsedMs.toFixed(1)), rssMiB: Number(rssMiB.toFixed(1)), thresholdMs: maxMs, status: elapsedMs <= maxMs && platform.store.counts().notes === targetItems ? "PASS" : "FAIL" };
  console.log(JSON.stringify(record, null, 2));
  if (record.status !== "PASS") process.exitCode = 1;
} finally { platform.close(); }
