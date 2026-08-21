let catalog = { entries: [] };
let state = {};
let side = "light";

const elements = Object.fromEntries(["count", "current", "game", "list", "mode", "preview", "search", "side", "status"]
  .map((id) => [id, document.getElementById(id)]));

async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function selectedEntry() {
  return catalog.entries.find((entry) => entry.id === state.selected) || catalog.entries[0] || null;
}

function renderPreview() {
  const entry = selectedEntry();
  elements.current.textContent = entry ? entry.fullLabel : "未选择";
  elements.preview.src = entry ? entry[side] : "";
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

async function update(patch) {
  try {
    state = await json("/api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    render();
  } catch (error) { elements.status.textContent = `保存失败：${error.message}`; }
}

async function load() {
  try {
    [catalog, state] = await Promise.all([json("/catalog.json"), json("/state.json")]);
    const games = [...new Map(catalog.entries.map((entry) => [entry.game, entry.gameName]))];
    for (const [value, label] of games) elements.game.add(new Option(label, value));
    render();
  } catch (error) { elements.status.textContent = `加载失败：${error.message}`; }
}

elements.search.addEventListener("input", renderList);
elements.game.addEventListener("change", renderList);
elements.side.addEventListener("click", () => { side = side === "light" ? "dark" : "light"; renderPreview(); });
elements.mode.addEventListener("click", () => update({ mode: state.mode === "rotate" ? "gallery" : "rotate" }));
load();
