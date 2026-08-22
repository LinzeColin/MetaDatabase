let catalog = { entries: [] };
let state = {};
let side = "light";
let syncSeen = -1;
let syncTimer = null;

const elements = Object.fromEntries(["count", "current", "game", "list", "mode", "next", "preview", "refresh", "search", "side", "status"]
  .map((id) => [id, document.getElementById(id)]));

async function json(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function selectedEntry() {
  return catalog.entries.find((entry) => entry.id === state.selected) || catalog.entries[0] || null;
}

function assetUrl(entry) {
  if (!entry) return "";
  const raw = entry[side];
  if (!raw || raw.includes("?v=") || !catalog.generated) return raw || "";
  return `${raw}?v=${encodeURIComponent(catalog.generated)}`;
}

function renderPreview() {
  const entry = selectedEntry();
  elements.current.textContent = entry ? entry.fullLabel : "未选择";
  elements.preview.src = assetUrl(entry);
  elements.preview.hidden = !entry;
  elements.mode.textContent = state.mode === "rotate" ? "停止轮播" : "开启轮播";
}

function renderList() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const game = elements.game.value;
  const visible = catalog.entries.filter((entry) => (!game || entry.game === game)
    && (!query || `${entry.fullLabel} ${entry.character} ${entry.variant}`.toLocaleLowerCase().includes(query)));
  elements.list.replaceChildren(...visible.map((entry) => {
    const button = document.createElement("button");
    button.className = "card";
    button.setAttribute("aria-current", String(entry.id === state.selected));
    button.innerHTML = `<strong></strong><small></small>`;
    button.querySelector("strong").textContent = entry.fullLabel;
    button.querySelector("small").textContent = entry.gameName;
    button.addEventListener("click", () => update({ selected: entry.id, mode: "gallery" }));
    return button;
  }));
  elements.count.textContent = `${visible.length} / ${catalog.count}`;
}

function render() { renderPreview(); renderList(); }

function renderGames() {
  const selected = elements.game.value;
  elements.game.replaceChildren(new Option("全部游戏", ""));
  for (const [value, label] of new Map(catalog.entries.map((entry) => [entry.game, entry.gameName]))) {
    elements.game.add(new Option(label, value));
  }
  if ([...elements.game.options].some((option) => option.value === selected)) elements.game.value = selected;
}

async function update(patch) {
  try {
    state = await json("/api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    syncSeen = state.updated || 0;
    render();
  } catch (error) { elements.status.textContent = `保存失败：${error.message}`; }
}

async function next() {
  try {
    state = await json("/api/next", { method: "POST" });
    syncSeen = state.updated || 0;
    render();
  } catch (error) { elements.status.textContent = `切换失败：${error.message}`; }
}

async function load() {
  try {
    [catalog, state] = await Promise.all([json("/catalog.json"), json("/state.json")]);
    renderGames();
    syncSeen = state.updated || 0;
    render();
    syncTimer = setInterval(sync, 1000);
  } catch (error) { elements.status.textContent = `加载失败：${error.message}`; }
}

async function sync() {
  try {
    const shared = await json("/state.json");
    const catalogChanged = Boolean(shared.catalogGenerated) && shared.catalogGenerated !== catalog.generated;
    if (!catalogChanged && (shared.updated || 0) === syncSeen) return;
    if (catalogChanged) {
      catalog = await json("/catalog.json");
      renderGames();
    }
    state = shared;
    syncSeen = shared.updated || 0;
    elements.status.textContent = "";
    render();
  } catch (error) { elements.status.textContent = `同步失败：${error.message}`; }
}

async function refreshCatalog() {
  elements.refresh.disabled = true;
  elements.status.textContent = "正在读取 SMB 素材目录…";
  const started = Date.now();
  try {
    await json("/api/catalog/refresh", { method: "POST" });
    while (Date.now() - started < 120000) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const status = await json("/refresh-status.json");
      elements.status.textContent = status.message || "正在同步…";
      if (status.status === "failed") throw new Error(status.message || "素材目录同步失败");
      if (status.status === "ready" && Number(status.updated) >= started) {
        await sync();
        return;
      }
    }
    throw new Error("素材目录仍在扫描，请稍后再看");
  } catch (error) {
    elements.status.textContent = `同步失败：${error.message}`;
  } finally {
    elements.refresh.disabled = false;
  }
}

elements.search.addEventListener("input", renderList);
elements.game.addEventListener("change", renderList);
elements.side.addEventListener("click", () => { side = side === "light" ? "dark" : "light"; renderPreview(); });
elements.mode.addEventListener("click", () => update({ mode: state.mode === "rotate" ? "gallery" : "rotate" }));
elements.next.addEventListener("click", next);
elements.refresh.addEventListener("click", refreshCatalog);
document.addEventListener("keydown", (event) => {
  if (event.repeat || event.altKey || !(event.metaKey || event.ctrlKey) || !event.shiftKey || event.key.toLocaleLowerCase() !== "n") return;
  event.preventDefault();
  next();
});
window.addEventListener("pagehide", () => { if (syncTimer) clearInterval(syncTimer); });
load();
