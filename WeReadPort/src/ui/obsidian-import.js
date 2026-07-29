import { readZipEntries } from "../core/zip.js";

const MAX_FILES = 1000;
const MAX_TOTAL = 50 * 1024 * 1024;
const ALLOWED = /\.(?:md|markdown|txt)$/i;

export async function readObsidianSelection(files) {
  const list = [...(files || [])];
  if (!list.length) throw new Error("请选择 Obsidian Vault 文件夹、ZIP 或 Markdown 文件。");
  const output = [];
  let total = 0;
  for (const file of list) {
    if (/\.zip$/i.test(file.name)) {
      const entries = await readZipEntries(new Uint8Array(await file.arrayBuffer()));
      for (const [entryPath, bytes] of entries) {
        if (!ALLOWED.test(entryPath) || unsafe(entryPath)) continue;
        total += bytes.length;
        output.push({ name: leaf(entryPath), path: entryPath, content: new TextDecoder("utf-8", { fatal: false }).decode(bytes) });
        enforce(output.length, total);
      }
      continue;
    }
    const relative = file.webkitRelativePath || file.name;
    if (!ALLOWED.test(relative) || unsafe(relative)) continue;
    const content = await file.text();
    total += new TextEncoder().encode(content).length;
    output.push({ name: file.name, path: relative, content });
    enforce(output.length, total);
  }
  if (!output.length) throw new Error("没有找到 Markdown 或 TXT 笔记。请选择 Vault 文件夹或导出的 ZIP。");
  return { items: output, sourceLabel: list.some(file => file.webkitRelativePath) ? "Obsidian Vault 文件夹" : "Obsidian 导出文件", totalFiles: output.length, totalBytes: total };
}
function enforce(count, total) { if (count > MAX_FILES) throw new Error(`一次最多导入 ${MAX_FILES} 个文本文件。`); if (total > MAX_TOTAL) throw new Error("一次导入内容不能超过 50 MB。"); }
function unsafe(value) { return String(value).replaceAll("\\", "/").split("/").some(part => !part || part === "." || part === ".."); }
function leaf(value) { return String(value).replaceAll("\\", "/").split("/").at(-1) || "未命名.md"; }
