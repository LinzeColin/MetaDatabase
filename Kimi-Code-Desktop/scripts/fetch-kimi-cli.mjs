import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import AdmZip from "adm-zip";

const VERSION = "0.38.0";
const TAG = `@moonshot-ai/kimi-code@${VERSION}`;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function option(name, fallback) {
  const prefix = `--${name}=`;
  const inline = process.argv.slice(2).find((value) => value.startsWith(prefix));
  if (inline) return inline.slice(prefix.length);
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const platform = option("platform", process.platform);
const arch = option("arch", process.arch);
if (![["darwin", "arm64"], ["win32", "x64"], ["win32", "arm64"]]
  .some(([candidatePlatform, candidateArch]) => candidatePlatform === platform && candidateArch === arch)) {
  throw new Error(`Unsupported Kimi CLI target: ${platform}-${arch}`);
}

const asset = `kimi-code-${platform}-${arch}.zip`;
const url = `https://github.com/MoonshotAI/kimi-code/releases/download/${encodeURIComponent(TAG)}/${asset}`;
const scratch = path.join(root, "vendor", "kimi", `${platform}-${arch}`);
const current = path.join(root, "vendor", "kimi", "current");
const archive = path.join(scratch, asset);

fs.rmSync(scratch, { recursive: true, force: true });
fs.rmSync(current, { recursive: true, force: true });
fs.mkdirSync(scratch, { recursive: true });
fs.mkdirSync(current, { recursive: true });

console.log(`Downloading Kimi Code CLI ${VERSION} for ${platform}-${arch}`);
const response = await fetch(url, { redirect: "follow" });
if (!response.ok) throw new Error(`Download failed: HTTP ${response.status} ${url}`);
fs.writeFileSync(archive, Buffer.from(await response.arrayBuffer()));

const zip = new AdmZip(archive);
zip.extractAllTo(scratch, true);
const wanted = platform === "win32" ? "kimi.exe" : "kimi";
const queue = [scratch];
let executable = null;
while (queue.length && !executable) {
  const directory = queue.shift();
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) queue.push(candidate);
    else if (entry.name === wanted) { executable = candidate; break; }
  }
}
if (!executable) throw new Error(`${wanted} was not found in ${asset}`);
const target = path.join(current, wanted);
fs.copyFileSync(executable, target);
if (platform !== "win32") fs.chmodSync(target, 0o755);
fs.writeFileSync(path.join(current, "VERSION"), `${VERSION}\n`);
fs.rmSync(scratch, { recursive: true, force: true });
console.log(`Prepared ${target}`);
