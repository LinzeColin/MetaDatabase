import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { APP_NAME, APP_VERSION, PROFILE_LABELS } from "../src/core/constants.js";
import { createDemoCaller } from "../src/core/demo.js";
import { collectNotebookSummaries, collectSnapshot } from "../src/core/collector.js";
import { buildExport } from "../src/core/exporter.js";
import { readZipEntries } from "../src/core/zip.js";

const root = new URL("../", import.meta.url);

test("产品入口与清单使用简体中文", async () => {
  const index = await readFile(new URL("index.html", root), "utf8");
  const manifest = JSON.parse(await readFile(new URL("public/manifest.webmanifest", root), "utf8"));
  const appSource = await readFile(new URL("src/ui/app.js", root), "utf8");
  assert.match(index, /<html lang="zh-CN">/u);
  assert.match(index, /微信读书笔记迁移/u);
  assert.equal(manifest.lang, "zh-CN");
  assert.match(manifest.name, /微信读书笔记迁移/u);
  assert.equal(APP_NAME, "微信读书笔记迁移");
  assert.equal(APP_VERSION, "v0.0.0.1.7");
  assert.ok(!appSource.includes("v${APP_VERSION}"), "版本号前不得重复添加 v");
});

test("全部导出格式在界面中以中文用途优先说明", () => {
  for (const label of Object.values(PROFILE_LABELS)) {
    assert.match(label, /^[\u3400-\u9fff]/u);
  }
});

test("导出包显示名与核心说明使用中文", async () => {
  const call = createDemoCaller();
  const summaries = await collectNotebookSummaries({ key: "demo-only", call });
  const snapshot = await collectSnapshot({ key: "demo-only", summaries, exportProfile: "portable-commonmark", call, includeReadingStatistics: true });
  const result = await buildExport(snapshot, { profile: "portable-commonmark", includeOfflineSearch: true });
  assert.match(result.filename, /^微信读书笔记迁移-/u);
  assert.equal(result.manifest.productName, "微信读书笔记迁移");
  const entries = await readZipEntries(result.bytes);
  assert.match(new TextDecoder().decode(entries.get("README.md")), /微信读书笔记迁移|导出包/u);
  assert.match(new TextDecoder().decode(entries.get("EXPORT_REPORT.md")), /导出报告/u);
  assert.match(new TextDecoder().decode(entries.get("offline\/index.html")), /离线笔记搜索/u);
});

test("核心用户界面不残留旧英文营销或流程文案", async () => {
  const ui = await readFile(new URL("src/ui/app.js", root), "utf8");
  for (const phrase of ["YOUR NOTES", "STEP 0", "Markdown Profile", "DESIGNED FOR PORTABILITY", "WeRead Port"]) {
    assert.equal(ui.includes(phrase), false, `残留短语：${phrase}`);
  }
  assert.match(ui, /用演示数据试一次/u);
  assert.match(ui, /下载完整迁移压缩包/u);
  assert.match(ui, /上传已有笔记/u);
  assert.match(ui, /复制提问词并打开 ChatGPT/u);
  assert.match(ui, /一次性会话/u);
});
