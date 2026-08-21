import fs from "node:fs";
import path from "node:path";

export const GAME_SLUGS = Object.freeze({
  "原神": "genshin",
  "崩铁": "hsr",
  "绝区零": "zzz",
  "鸣潮": "wuwa",
  "异环": "nte",
});

function directories(root) {
  try {
    return fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
      .map((entry) => entry.name)
      .sort((left, right) => left.localeCompare(right, "zh"));
  } catch {
    return [];
  }
}

function readMeta(file) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { return {}; }
}

function encodeAssetUrl(baseUrl, gameName, character, variant, side) {
  const segments = [gameName, character, variant, side].map(encodeURIComponent);
  return `${baseUrl.replace(/\/$/, "")}/assets/${segments.join("/")}`;
}

export function buildCatalog({ sourceRoot, baseUrl = "http://127.0.0.1:3099", labels = {}, clock = () => new Date() }) {
  const entries = [];
  for (const [gameName, game] of Object.entries(GAME_SLUGS)) {
    const gameRoot = path.join(sourceRoot, gameName);
    for (const character of directories(gameRoot)) {
      const skinsRoot = path.join(gameRoot, character, "skins");
      for (const variant of directories(skinsRoot)) {
        const variantRoot = path.join(skinsRoot, variant);
        const lightFile = path.join(variantRoot, "light.png");
        const darkFile = path.join(variantRoot, "dark.png");
        if (!fs.existsSync(lightFile) || !fs.existsSync(darkFile)) continue;
        const id = `${game}/${character}/${variant}`;
        const meta = readMeta(path.join(variantRoot, "meta.json"));
        const label = labels[id] || {};
        const characterZh = label.characterZh || meta.characterZh || character;
        const variantZh = label.variantZh || meta.variantZh || (variant === "default" ? "默认" : variant);
        entries.push({
          id,
          game,
          gameName,
          character,
          variant,
          characterZh,
          variantZh,
          label: characterZh,
          fullLabel: variant === "default" ? characterZh : `${characterZh} · ${variantZh}`,
          light: encodeAssetUrl(baseUrl, gameName, character, variant, "light"),
          dark: encodeAssetUrl(baseUrl, gameName, character, variant, "dark"),
        });
      }
    }
  }
  entries.sort((left, right) => left.fullLabel.localeCompare(right.fullLabel, "zh"));
  return {
    version: 1,
    source: "smb",
    generated: clock().toISOString(),
    count: entries.length,
    entries,
  };
}

export function assetPath(sourceRoot, requestPath) {
  const match = requestPath.match(/^\/assets\/([^/]+)\/([^/]+)\/([^/]+)\/(light|dark)$/);
  if (!match) return null;
  const [, rawGame, rawCharacter, rawVariant, side] = match;
  const values = [rawGame, rawCharacter, rawVariant].map((value) => decodeURIComponent(value));
  if (values.some((value) => !value || value === "." || value === ".." || value.includes("/") || value.includes("\\"))) return null;
  const [gameName, character, variant] = values;
  if (!GAME_SLUGS[gameName]) return null;
  return path.join(sourceRoot, gameName, character, "skins", variant, `${side}.png`);
}
