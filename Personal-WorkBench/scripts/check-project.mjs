import { readdir, readFile, stat } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const sourceRoots = ["app", "db", "scripts", ".openai"];
const sourceExtensions = new Set([".ts", ".tsx", ".mjs", ".js", ".json"]);
const ignoredDirectories = new Set(["node_modules", ".next", ".vinext", "dist", ".wrangler"]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function collectFiles(path) {
  const info = await stat(path);
  if (info.isFile()) {
    return sourceExtensions.has(path.slice(path.lastIndexOf("."))) ? [path] : [];
  }

  const entries = await readdir(path, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (entry.isDirectory() && ignoredDirectories.has(entry.name)) continue;
    files.push(...(await collectFiles(join(path, entry.name))));
  }
  return files;
}

const hostingPath = join(root, ".openai", "hosting.json");
const hosting = JSON.parse(await readFile(hostingPath, "utf8"));
assert(typeof hosting.project_id === "string" && /^appgprj_[A-Za-z0-9]+$/.test(hosting.project_id), "hosting.json must contain the exact opaque Sites project_id");
assert(hosting.d1 === "DB", "hosting.json d1 binding must be DB");
assert(hosting.r2 === "FILES", "hosting.json r2 binding must be FILES");
assert(!JSON.stringify(hosting).toLowerCase().includes("weread"), "hosting.json must not reuse a WeRead linkage");

const files = (await Promise.all(sourceRoots.map((name) => collectFiles(join(root, name))))).flat();
const source = await Promise.all(files.map(async (path) => ({ path, text: await readFile(path, "utf8") })));
const secretPatterns = [
  ["private key", /-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----/],
  ["OpenAI-style key", /\bsk-[A-Za-z0-9_-]{16,}\b/],
  ["GitHub-style token", /\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}\b/],
];
for (const [label, pattern] of secretPatterns) {
  const matched = source.find((entry) => pattern.test(entry.text));
  assert(!matched, `${label} found in ${relative(root, matched?.path ?? root)}`);
}

const [pageSource, layoutSource, packageJson] = await Promise.all([
  readFile(join(root, "app", "page.tsx"), "utf8"),
  readFile(join(root, "app", "layout.tsx"), "utf8"),
  readFile(join(root, "package.json"), "utf8"),
]);
assert(!pageSource.includes("SkeletonPreview"), "S1 must replace the Sites starter skeleton");
assert(!pageSource.includes("codex-preview"), "product pages must not retain preview metadata");
assert(!layoutSource.includes("Starter Project"), "layout metadata must name the product");
assert(!packageJson.includes("react-loading-skeleton"), "S1 must remove the disposable skeleton dependency");
assert(/[\u3400-\u9fff]/.test(pageSource), "finished product UI must include Chinese visible copy");
assert(pageSource.includes("data-reference-page"), "reference-mode route markers are required for visual QA");

try {
  await stat(join(root, "app", "_sites-preview"));
  throw new Error("S1 must remove app/_sites-preview");
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}

console.log(
  JSON.stringify({
    status: "PASS",
    stage: "S1",
    starter_skeleton: false,
    hosting_bindings: { d1: hosting.d1, r2: hosting.r2 },
    source_files_checked: files.length,
  }),
);
