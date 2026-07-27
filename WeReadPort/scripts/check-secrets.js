import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const files = (await walk(root)).filter(file => !file.includes(`${path.sep}dist${path.sep}`) && !file.includes(`${path.sep}__pycache__${path.sep}`) && !/\.(zip|png|jpg|jpeg|gif|webp|ico|pyc)$/i.test(file));
const patterns = [
  { name: "probable WeRead user key", regex: /wrk-[A-Za-z0-9_-]{20,}/g },
  { name: "private key block", regex: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g },
  { name: "GitHub token", regex: /gh[pousr]_[A-Za-z0-9]{30,}/g },
  { name: "Google client secret", regex: /GOCSPX-[A-Za-z0-9_-]{20,}/g }
];
let failures = 0;
for (const file of files) { let text; try { text = await readFile(file, "utf8"); } catch { continue; } for (const pattern of patterns) { if (pattern.regex.test(text)) { console.error(`${pattern.name}: ${path.relative(root, file)}`); failures += 1; } pattern.regex.lastIndex = 0; } }
if (failures) process.exit(1);
console.log(`敏感信息扫描通过： ${files.length} 个文本文件。`);
async function walk(dir) { const out = []; for (const entry of await readdir(dir, { withFileTypes: true })) { if (["node_modules", ".git"].includes(entry.name)) continue; const full = path.join(dir, entry.name); if (entry.isDirectory()) out.push(...await walk(full)); else out.push(full); } return out; }
