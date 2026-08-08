import { existsSync, statSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const mockUrl = new URL("./cloudflare-workers-mock.mjs", import.meta.url).href;
const projectRoot = new URL("../", import.meta.url).href;
const candidates = [".ts", ".mts", ".js", ".jsx", ".mjs", ".tsx", ".json"];

function resolveSourceSpecifier(maybeUrl) {
  const basePath = fileURLToPath(maybeUrl);
  if (existsSync(basePath) && statSync(basePath).isFile()) {
    return maybeUrl.href;
  }
  for (const ext of candidates) {
    const filePath = `${basePath}${ext}`;
    if (existsSync(filePath)) {
      return pathToFileURL(filePath).href;
    }
  }
  for (const ext of candidates) {
    const indexPath = `${basePath}/index${ext}`;
    if (existsSync(indexPath)) {
      return pathToFileURL(indexPath).href;
    }
  }
  return null;
}

function resolveAliasSpecifier(specifier) {
  const maybeUrl = new URL(specifier.slice(2), projectRoot);
  return resolveSourceSpecifier(maybeUrl) ?? maybeUrl.href;
}

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "cloudflare:workers") return { url: mockUrl, shortCircuit: true };
  if (specifier.startsWith("@/")) {
    return { url: resolveAliasSpecifier(specifier), shortCircuit: true };
  }
  if (specifier.startsWith("./") || specifier.startsWith("../")) {
    const resolved = resolveSourceSpecifier(new URL(specifier, context.parentURL));
    if (resolved) return { url: resolved, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
