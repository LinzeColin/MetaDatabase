#!/usr/bin/env node
import { mkdir, readFile, rename, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { collectNotebookSummaries, collectSnapshot } from "../src/core/collector.js";
import { EXPORT_PROFILES, PROFILE_LABELS } from "../src/core/constants.js";
import { createDemoCaller } from "../src/core/demo.js";
import { toSafeFailure, WeReadPortError } from "../src/core/errors.js";
import { buildExport } from "../src/core/exporter.js";
import { createCollectorCaller, createGatewayClient } from "../src/core/gateway.js";

process.umask(0o077);

const profileAliases = Object.freeze({
  portable: EXPORT_PROFILES.PORTABLE,
  commonmark: EXPORT_PROFILES.PORTABLE,
  gfm: EXPORT_PROFILES.GFM,
  obsidian: EXPORT_PROFILES.OBSIDIAN,
  notion: EXPORT_PROFILES.NOTION,
  [EXPORT_PROFILES.PORTABLE]: EXPORT_PROFILES.PORTABLE,
  [EXPORT_PROFILES.GFM]: EXPORT_PROFILES.GFM,
  [EXPORT_PROFILES.OBSIDIAN]: EXPORT_PROFILES.OBSIDIAN,
  [EXPORT_PROFILES.NOTION]: EXPORT_PROFILES.NOTION,
});

try {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(helpText());
    process.exit(0);
  }

  const call = options.demo ? createDemoCaller() : createCollectorCaller(createGatewayClient({ mode: "direct" }));
  const key = options.demo ? "demo-only" : String(process.env.WEREAD_API_KEY ?? "");
  if (!options.demo && !key) throw new WeReadPortError("AUTH", "请先在当前终端设置 WEREAD_API_KEY；不要把密钥写进命令参数、代码或任务包。");

  const summaries = await collectNotebookSummaries({
    key,
    call,
    onProgress: message => process.stderr.write(`${message}\n`),
  });

  if (options.list) {
    printBookList(summaries);
    process.exit(0);
  }
  if (!summaries.length) throw new WeReadPortError("NO_EXPORTABLE_DATA", "账号当前没有可导出的个人笔记。");

  const selected = options.bookIds.length
    ? summaries.filter(summary => options.bookIds.includes(summary.bookId))
    : summaries;
  const missing = options.bookIds.filter(bookId => !selected.some(summary => summary.bookId === bookId));
  if (missing.length) throw new WeReadPortError("NO_SELECTION", `未在笔记本中找到 bookId：${missing.join(", ")}`);

  const snapshot = await collectSnapshot({
    key,
    summaries: selected,
    exportProfile: options.profile,
    call,
    includeReadingStatistics: options.includeReadingStatistics,
    onProgress: (done, total, title) => process.stderr.write(`读取 ${done}/${total}：《${title}》\n`),
  });

  const previousZip = options.previous ? new Uint8Array(await readFile(options.previous)) : undefined;
  const result = await buildExport(snapshot, {
    profile: options.profile,
    includeCover: options.includeCover,
    includeOfflineSearch: options.includeOfflineSearch,
    previousZip,
    knownSourceBookIds: summaries.map(summary => summary.bookId),
    sourceInventoryComplete: true,
  });

  const destination = await resolveDestination(options.output, result.filename);
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.tmp-${process.pid}-${Date.now()}`;
  try {
    await writeFile(temporary, result.bytes, { mode: 0o600, flag: "wx" });
    await rename(temporary, destination);
  } catch (error) {
    await unlink(temporary).catch(() => {});
    throw error;
  }

  process.stdout.write(`${destination}\n`);
  process.stderr.write(`完成：${result.status} · ${result.manifest.updatedBookCount} 本更新 · ${result.manifest.retainedBookCount} 本保留 · ${result.manifest.tombstoneCount} 本上游消失存档 · ${result.bytes.byteLength} 字节 · ${PROFILE_LABELS[options.profile]}\n`);
} catch (error) {
  const safe = toSafeFailure(error);
  process.stderr.write(`[${safe.code}] ${safe.message}\n`);
  process.exitCode = 1;
}

function parseArgs(args) {
  const options = {
    demo: false,
    help: false,
    list: false,
    bookIds: [],
    profile: EXPORT_PROFILES.PORTABLE,
    output: ".",
    previous: undefined,
    includeOfflineSearch: true,
    includeReadingStatistics: true,
    includeCover: false,
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--demo") options.demo = true;
    else if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--list") options.list = true;
    else if (arg === "--book") options.bookIds.push(requireValue(args, ++index, arg));
    else if (arg === "--profile") {
      const raw = requireValue(args, ++index, arg).toLowerCase();
      if (!profileAliases[raw]) throw new WeReadPortError("CLI", `未知 profile：${raw}`);
      options.profile = profileAliases[raw];
    } else if (arg === "--output" || arg === "-o") options.output = requireValue(args, ++index, arg);
    else if (arg === "--previous") options.previous = requireValue(args, ++index, arg);
    else if (arg === "--no-offline-search") options.includeOfflineSearch = false;
    else if (arg === "--no-reading-stats") options.includeReadingStatistics = false;
    else if (arg === "--include-cover") options.includeCover = true;
    else throw new WeReadPortError("CLI", `未知参数：${arg}`);
  }
  return options;
}

function requireValue(args, index, flag) {
  const value = args[index];
  if (!value || value.startsWith("--")) throw new WeReadPortError("CLI", `${flag} 缺少参数值。`);
  return value;
}

async function resolveDestination(raw, generatedName) {
  const absolute = path.resolve(raw || ".");
  try {
    const info = await stat(absolute);
    if (info.isDirectory()) return path.join(absolute, generatedName);
  } catch { /* A non-existent path can still be an intended file. */ }
  return absolute.toLowerCase().endsWith(".zip") ? absolute : path.join(absolute, generatedName);
}

function printBookList(summaries) {
  const rows = summaries.map(summary => ({
    bookId: summary.bookId,
    title: summary.title,
    author: summary.author || "—",
    notes: summary.totalNoteCount,
    progress: summary.readingProgress === undefined ? "—" : `${summary.readingProgress}%`,
  }));
  console.table(rows);
}

function helpText() {
  return `微信读书笔记迁移命令行工具\n\n用法：\n  WEREAD_API_KEY='你的用户密钥' npm run export -- [选项]\n  npm run export -- --demo --output ./exports\n\n选项：\n  --list                    仅列出有笔记的书籍\n  --book <bookId>           只导出指定书；可重复\n  --profile <name>          portable|gfm|obsidian|notion\n  --output, -o <path>       输出目录或 .zip 文件路径\n  --previous <zip>          读取上次导出并保留个人补充区\n  --include-cover           在 标记文本 中保留封面链接\n  --no-offline-search       不生成离线搜索页\n  --no-reading-stats        不读取总体阅读统计\n  --demo                    使用完全虚构的本地演示数据\n  --help, -h                显示帮助\n\n安全规则：密钥只能从 WEREAD_API_KEY 环境变量读取，不能通过命令参数传入。\n`;
}
