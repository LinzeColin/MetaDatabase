import { readFileSync, unwatchFile, watchFile } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const BASE = "http://127.0.0.1:3099";

function readJson(filename, fallback) {
  try { return JSON.parse(readFileSync(filename, "utf8")); }
  catch { return fallback; }
}

function text(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function command(label, invoke = () => {}, options = {}) {
  return {
    label: () => label,
    invoke,
    ...options.enabled === undefined ? {} : { enabled: () => options.enabled },
    ...options.type === undefined ? {} : { type: options.type },
    ...options.checked === undefined ? {} : { checked: () => options.checked },
  };
}

function nested(label, submenu) {
  return { label: () => label, submenu: () => submenu };
}

function separator() { return { type: "separator" }; }

async function postJSON(route, body = {}) {
  const response = await fetch(`${BASE}${route}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Harness UI ${route} returned HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function openHarnessLibrary() {
  const child = spawn("/usr/bin/open", ["harnessui://library"], { detached: true, stdio: "ignore" });
  child.unref();
}

export function readHarnessSnapshot(dataRoot = path.join(homedir(), ".harness-ui")) {
  return {
    catalog: readJson(path.join(dataRoot, "catalog.json"), { count: 0, entries: [] }),
    state: readJson(path.join(dataRoot, "state.json"), {}),
    refresh: readJson(path.join(dataRoot, "refresh-status.json"), {}),
  };
}

export function buildHarnessSubmenu({
  dataRoot = path.join(homedir(), ".harness-ui"),
  locale = "zh",
  request = postJSON,
  openLibrary = openHarnessLibrary,
} = {}) {
  const zh = locale === "zh";
  const { catalog, state, refresh } = readHarnessSnapshot(dataRoot);
  const entries = Array.isArray(catalog.entries) ? catalog.entries : [];
  const selected = entries.find((entry) => entry.id === state.selected);
  const items = [
    command(zh ? `素材库：${entries.length} 个变体` : `Library: ${entries.length} variants`, () => {}, { enabled: false }),
    command(zh ? `当前：${text(selected?.fullLabel, "未选择")}` : `Current: ${text(selected?.fullLabel, "None")}`, () => {}, { enabled: false }),
  ];
  if (["partial", "failed"].includes(refresh.status) && text(refresh.message)) {
    items.push(command(zh ? `同步状态：${text(refresh.message)}` : `Sync: ${text(refresh.message)}`, () => {}, { enabled: false }));
  }
  items.push(
    separator(),
    command(zh ? "打开完整素材库" : "Open Full Library", openLibrary),
    command(zh ? "立即同步 SMB 素材目录" : "Sync SMB Library Now", () => request("/api/catalog/refresh")),
    command(state.mode === "rotate" ? (zh ? "停止轮播" : "Stop Rotation") : (zh ? "开启轮播" : "Start Rotation"),
      () => request("/api/state", { mode: state.mode === "rotate" ? "gallery" : "rotate" })),
    command(zh ? "换下一张（⌘⇧N）" : "Next Skin (⌘⇧N)", () => request("/api/next"), { enabled: entries.length > 0 }),
    separator(),
  );

  const games = new Map();
  for (const entry of entries) {
    const gameKey = text(entry.game, "unknown");
    if (!games.has(gameKey)) games.set(gameKey, { label: text(entry.gameName, gameKey), characters: new Map() });
    const game = games.get(gameKey);
    const characterKey = text(entry.character, text(entry.characterZh, entry.id));
    if (!game.characters.has(characterKey)) game.characters.set(characterKey, []);
    game.characters.get(characterKey).push(entry);
  }

  const gameMenus = [...games.values()].sort((left, right) => left.label.localeCompare(right.label, "zh"));
  for (const game of gameMenus) {
    const characters = [...game.characters.values()].map((variants) => {
      variants.sort((left, right) => text(left.variantZh, left.variant).localeCompare(text(right.variantZh, right.variant), "zh"));
      if (variants.length === 1) {
        const entry = variants[0];
        return command(text(entry.fullLabel, text(entry.characterZh, entry.character)),
          () => request("/api/state", { mode: "gallery", selected: entry.id }),
          { type: "checkbox", checked: entry.id === state.selected });
      }
      return nested(text(variants[0].characterZh, variants[0].character), variants.map((entry) =>
        command(text(entry.variantZh, entry.variant),
          () => request("/api/state", { mode: "gallery", selected: entry.id }),
          { type: "checkbox", checked: entry.id === state.selected })));
    });
    characters.sort((left, right) => left.label().localeCompare(right.label(), "zh"));
    items.push(nested(game.label, characters));
  }
  if (!entries.length) items.push(command(zh ? "暂无可用素材" : "No Skins Available", () => {}, { enabled: false }));
  return items;
}

export function registerHarnessMenu(ctx, options = {}) {
  const dataRoot = options.dataRoot || path.join(homedir(), ".harness-ui");
  const registration = ctx.desktopRuntime.registerTrayItem({
    group: "harness",
    order: 10,
    label: () => ctx.desktopRuntime.locale === "zh" ? "皮肤" : "Skins",
    submenu: () => buildHarnessSubmenu({ ...options, dataRoot, locale: ctx.desktopRuntime.locale }),
  });
  let refreshQueued = false;
  const refresh = () => {
    if (refreshQueued) return;
    refreshQueued = true;
    queueMicrotask(() => {
      refreshQueued = false;
      registration.refresh();
    });
  };
  const watched = ["catalog.json", "state.json", "refresh-status.json"].map((name) => path.join(dataRoot, name));
  for (const filename of watched) watchFile(filename, { interval: 1000, persistent: false }, refresh);
  return () => {
    for (const filename of watched) unwatchFile(filename, refresh);
    registration.dispose();
  };
}
