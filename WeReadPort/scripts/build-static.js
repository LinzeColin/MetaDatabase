import { cp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.resolve(process.env.WEREAD_PORT_PORTABLE_DIST || path.join(root, "dist"));
if (dist === root || !dist) throw new Error("Portable output must be a separate directory.");
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(path.join(root, "index.html"), path.join(dist, "index.html"));
await cp(path.join(root, "public"), dist, { recursive: true });
await mkdir(path.join(dist, "src"), { recursive: true });
await cp(path.join(root, "src", "core"), path.join(dist, "src", "core"), { recursive: true });
await cp(path.join(root, "src", "ui"), path.join(dist, "src", "ui"), { recursive: true });
await mkdir(path.join(dist, ".openai"), { recursive: true });
await cp(path.join(root, ".openai", "hosting.json"), path.join(dist, ".openai", "hosting.json"));
for (const route of ["privacy", "terms"]) {
  await mkdir(path.join(dist, route), { recursive: true });
  await cp(path.join(root, "index.html"), path.join(dist, route, "index.html"));
}
const files = await walk(dist);
await writeFile(path.join(dist, "build-manifest.json"), `${JSON.stringify({ generatedBy: "scripts/build-static.js", files: files.sort() }, null, 2)}\n`);
console.log(`Built ${files.length + 1} static files in ${dist}`);
async function walk(dir, prefix = "") {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const rel = path.posix.join(prefix, entry.name);
    if (entry.isDirectory()) out.push(...await walk(path.join(dir, entry.name), rel));
    else out.push(rel);
  }
  return out;
}
