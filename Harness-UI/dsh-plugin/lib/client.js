window.__ModuleLoader__.load({
  id: "dsh-harness-ui-skins",
  factory: (_require) => {
    const module = { exports: {} };
    const inject = [];
    const BASE = "http://127.0.0.1:3099";
    const SYNC_MS = 1000;

    function styleSheet() {
      const element = document.createElement("style");
      element.id = "harness-ui-dsh-style";
      element.textContent = `
body[data-dsh-harness-ui],html:has(body[data-dsh-harness-ui]){background:transparent!important}
body[data-dsh-harness-ui] [id=root],body[data-dsh-harness-ui] #app{
  background-image:linear-gradient(to right,rgba(255,255,255,.62),rgba(255,255,255,0) 30%,rgba(255,255,255,.76) 100%),var(--harness-scene)!important;
  background-size:cover!important;background-position:center!important;background-repeat:no-repeat!important;background-color:#e8eef7!important
}
body[data-dsh-harness-ui][data-ds-dark-theme] [id=root],body[data-dsh-harness-ui][data-ds-dark-theme] #app{
  background-image:linear-gradient(to right,rgba(10,14,24,.66),rgba(10,14,24,0) 30%,rgba(10,14,24,.78) 100%),var(--harness-scene)!important;background-color:#0d1117!important
}
body[data-dsh-harness-ui] [id=root] *{background-color:transparent!important}
body[data-dsh-harness-ui] :is(input,textarea,select,[role=dialog],[role=menu],[role=listbox],pre,code){background-color:rgba(245,248,255,.84)!important}
body[data-dsh-harness-ui][data-ds-dark-theme] :is(input,textarea,select,[role=dialog],[role=menu],[role=listbox],pre,code){background-color:rgba(15,22,38,.82)!important}
#harness-ui-toggle{position:fixed;right:16px;bottom:16px;z-index:2147483000;border:1px solid #ffffff35;border-radius:999px;padding:7px 12px;background:#101826e8;color:#fff;cursor:pointer}
#harness-ui-picker{position:fixed;right:16px;bottom:54px;z-index:2147483000;width:min(620px,72vw);max-height:65vh;display:none;overflow:auto;border:1px solid #ffffff38;border-radius:14px;padding:12px;background:#101826f4;color:#e8eef7;box-shadow:0 24px 80px #000b;font:13px/1.45 system-ui,-apple-system,"PingFang SC",sans-serif}
#harness-ui-picker[data-open=true]{display:block}
#harness-ui-bar{position:sticky;top:-12px;display:flex;flex-wrap:wrap;gap:7px;align-items:center;padding:10px 0;background:#101826fa}
#harness-ui-bar :is(input,select,button){border:1px solid #ffffff2c;border-radius:7px;padding:5px 8px;background:#0b1220!important;color:#e8eef7;cursor:pointer}
#harness-ui-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:7px}
#harness-ui-list button{min-height:48px;text-align:left;border:1px solid #ffffff22;border-radius:8px;padding:7px 9px;background:#172238!important;color:#e8eef7;cursor:pointer}
#harness-ui-list button[data-active=true]{border-color:#7aa2ff;background:#1a2d55!important}
#harness-ui-list small{display:block;color:#9fb0cf}
#harness-ui-status{margin-left:auto;color:#aab9d4;font-size:11px}
`;
      return element;
    }

    async function json(path, options) {
      const response = await fetch(`${BASE}${path}`, { cache: "no-store", ...options });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.status === 204 ? null : response.json();
    }

    function preload(url) {
      return new Promise((resolve) => {
        const image = new Image();
        const timer = setTimeout(() => resolve(false), 15000);
        image.onload = () => { clearTimeout(timer); resolve(true); };
        image.onerror = () => { clearTimeout(timer); resolve(false); };
        image.src = url;
      });
    }

    function apply() {
      let catalog = { entries: [] };
      let state = {};
      let syncTimer = null;
      let syncSeen = -1;
      let showRevision = 0;
      const root = document.documentElement;
      document.body.dataset.dshHarnessUi = "";
      if (!document.getElementById("harness-ui-dsh-style")) document.head.appendChild(styleSheet());

      const toggle = document.createElement("button");
      toggle.id = "harness-ui-toggle";
      toggle.type = "button";
      toggle.textContent = "皮肤";
      const panel = document.createElement("section");
      panel.id = "harness-ui-picker";
      panel.innerHTML = `<div id="harness-ui-bar">
        <select data-hu="game"><option value="">全部游戏</option></select>
        <input data-hu="search" type="search" placeholder="搜索角色或变体">
        <button data-hu="mode" type="button">开启轮播</button>
        <button data-hu="next" type="button">下一张</button>
        <button data-hu="refresh" type="button">同步素材</button>
        <span id="harness-ui-status"></span>
      </div><div id="harness-ui-list"></div>`;
      document.body.append(toggle, panel);

      const game = panel.querySelector('[data-hu="game"]');
      const search = panel.querySelector('[data-hu="search"]');
      const mode = panel.querySelector('[data-hu="mode"]');
      const list = panel.querySelector("#harness-ui-list");
      const status = panel.querySelector("#harness-ui-status");
      const byId = (id) => catalog.entries.find((entry) => entry.id === id) || catalog.entries[0] || null;
      const dark = () => document.body.hasAttribute("data-ds-dark-theme");

      function assetUrl(entry) {
        if (!entry) return "";
        const raw = dark() ? entry.dark : entry.light;
        if (!raw) return "";
        const revisioned = raw.includes("?v=") || !catalog.generated
          ? raw
          : `${raw}?v=${encodeURIComponent(catalog.generated)}`;
        return `${revisioned}${revisioned.includes("?") ? "&" : "?"}skin=${encodeURIComponent(entry.id)}`;
      }

      function renderGames() {
        const selected = game.value;
        game.replaceChildren(new Option("全部游戏", ""));
        for (const [value, label] of new Map(catalog.entries.map((entry) => [entry.game, entry.gameName]))) {
          game.add(new Option(label, value));
        }
        if ([...game.options].some((option) => option.value === selected)) game.value = selected;
      }

      async function show(entry) {
        const revision = ++showRevision;
        if (!entry) {
          root.style.removeProperty("--harness-scene");
          return;
        }
        const url = assetUrl(entry);
        if (await preload(url) && revision === showRevision)
          root.style.setProperty("--harness-scene", `url(${JSON.stringify(url)})`);
      }

      function renderList() {
        const term = search.value.trim().toLocaleLowerCase();
        const entries = catalog.entries.filter((entry) => (!game.value || entry.game === game.value)
          && (!term || `${entry.fullLabel} ${entry.character} ${entry.variant}`.toLocaleLowerCase().includes(term)));
        list.replaceChildren(...entries.map((entry) => {
          const button = document.createElement("button");
          button.type = "button";
          button.dataset.active = String(entry.id === state.selected);
          button.innerHTML = "<strong></strong><small></small>";
          button.querySelector("strong").textContent = entry.fullLabel;
          button.querySelector("small").textContent = entry.gameName;
          button.addEventListener("click", () => update({ mode: "gallery", selected: entry.id }));
          return button;
        }));
        status.textContent = `${entries.length} / ${catalog.count || 0}`;
      }

      function render() {
        mode.textContent = state.mode === "rotate" ? "停止轮播" : "开启轮播";
        renderList();
        show(byId(state.selected));
      }

      async function update(patch) {
        try {
          state = await json("/api/state", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
          });
          if (state.catalogGenerated && state.catalogGenerated !== catalog.generated) {
            catalog = await json("/catalog.json");
            renderGames();
          }
          syncSeen = state.updated || 0;
          render();
        } catch (error) { status.textContent = `保存失败：${error.message}`; }
      }

      async function next() {
        try {
          state = await json("/api/next", { method: "POST" });
          syncSeen = state.updated || 0;
          render();
        } catch (error) { status.textContent = `切换失败：${error.message}`; }
      }

      async function refreshCatalog() {
        const started = Date.now();
        await json("/api/catalog/refresh", { method: "POST" });
        status.textContent = "正在读取并部署 SMB 素材…";
        while (Date.now() - started < 900000) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
          const refresh = await json("/refresh-status.json");
          status.textContent = refresh.message || "正在读取并部署 SMB 素材…";
          if (refresh.status === "failed") throw new Error(refresh.message || "素材目录同步失败");
          if (["ready", "partial"].includes(refresh.status) && Number(refresh.updated) >= started) {
            [catalog, state] = await Promise.all([json("/catalog.json"), json("/state.json")]);
            renderGames();
            syncSeen = state.updated || 0;
            render();
            status.textContent = refresh.status === "partial" ? refresh.message : "素材已同步";
            return;
          }
        }
        throw new Error("素材目录仍在扫描，请稍后重试");
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
          render();
        } catch { status.textContent = "Harness UI 控制器未运行"; }
      }

      toggle.addEventListener("click", () => { panel.dataset.open = String(panel.dataset.open !== "true"); });
      game.addEventListener("change", renderList);
      search.addEventListener("input", renderList);
      mode.addEventListener("click", () => update({ mode: state.mode === "rotate" ? "gallery" : "rotate" }));
      panel.querySelector('[data-hu="next"]').addEventListener("click", next);
      panel.querySelector('[data-hu="refresh"]').addEventListener("click", async () => {
        try { await refreshCatalog(); }
        catch (error) { status.textContent = `同步失败：${error.message}`; }
      });

      (async () => {
        try {
          [catalog, state] = await Promise.all([json("/catalog.json"), json("/state.json")]);
          renderGames();
          syncSeen = state.updated || 0;
          render();
          syncTimer = setInterval(sync, SYNC_MS);
        } catch { status.textContent = "Harness UI 控制器未运行"; }
      })();

      const observer = new MutationObserver(() => show(byId(state.selected)));
      observer.observe(document.body, { attributes: true, attributeFilter: ["data-ds-dark-theme"] });
      const shortcut = (event) => {
        if (event.repeat || event.altKey || !(event.metaKey || event.ctrlKey) || !event.shiftKey || event.key.toLocaleLowerCase() !== "n") return;
        event.preventDefault();
        event.stopPropagation();
        next();
      };
      document.addEventListener("keydown", shortcut, true);

      return () => {
        if (syncTimer) clearInterval(syncTimer);
        observer.disconnect();
        document.removeEventListener("keydown", shortcut, true);
        toggle.remove();
        panel.remove();
        document.getElementById("harness-ui-dsh-style")?.remove();
        document.body.removeAttribute("data-dsh-harness-ui");
        root.style.removeProperty("--harness-scene");
      };
    }

    module.exports = { apply, inject };
    return module.exports;
  },
});
