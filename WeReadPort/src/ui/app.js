import {
  APP_NAME,
  APP_VERSION,
  CHATGPT_HANDOFF_URL,
  EXPORT_PROFILES,
  MAX_LOCAL_IMPORT_FILE_BYTES,
  MAX_LOCAL_IMPORT_FILES,
  MAX_LOCAL_IMPORT_TOTAL_BYTES,
  MAX_PREVIOUS_ARCHIVE_BYTES,
  PROFILE_LABELS,
  SOURCE_SKILL_VERSION,
} from "../core/constants.js";
import { validateLocalFileDescriptors } from "../core/local-import.js";

const app = document.querySelector("#app");
const path = location.pathname.replace(/\/+$/, "") || "/";
if (path === "/privacy") renderLegal("privacy");
else if (path === "/terms") renderLegal("terms");
else renderProduct();

function renderProduct() {
  app.innerHTML = `
    <a class="skip-link" href="#export-workspace">跳到迁移工具</a>
    <header class="topbar">
      <a class="brand" href="/" aria-label="${APP_NAME}首页">
        <span class="brand-mark" aria-hidden="true">阅</span>
        <span class="brand-copy"><strong>${APP_NAME}</strong><small>上传、整理、下载并继续询问</small></span>
      </a>
      <div class="header-trust" aria-label="隐私状态"><span class="status-dot" aria-hidden="true"></span>密钥、上传文件与笔记默认不落库</div>
      <nav aria-label="站点导航"><a href="#how">输出内容</a><a href="/privacy">隐私</a><a href="/terms">条款</a><a href="/healthz">系统状态</a></nav>
    </header>

    <main>
      <section class="hero" aria-labelledby="page-title">
        <div class="hero-copy">
          <p class="eyebrow">你的笔记 · 你的文件 · 由你掌控</p>
          <h1 id="page-title">把阅读带走。<br><span>继续在 ChatGPT 里追问。</span></h1>
          <p class="hero-lede">连接本人微信读书、上传已有笔记，或先用演示数据体验。系统会在浏览器内整理为中文标记文本、结构化数据、离线搜索和可校验压缩包，并额外生成一份适合上传到 ChatGPT 的单文件笔记。</p>
          <div class="hero-actions">
            <button id="hero-demo" class="button primary" type="button">用演示数据试一次 <span aria-hidden="true">→</span></button>
            <button id="hero-upload" class="button secondary" type="button">上传已有笔记</button>
            <button id="hero-connect" class="button ghost" type="button">连接我的微信读书</button>
          </div>
          <ul class="trust-list" aria-label="产品边界">
            <li><span aria-hidden="true">✓</span>本地文件只在浏览器中读取</li>
            <li><span aria-hidden="true">✓</span>完整导出与单文件下载</li>
            <li><span aria-hidden="true">✓</span>安全跳转到用户自己的 ChatGPT</li>
          </ul>
        </div>
        <aside class="hero-proof" aria-label="一次迁移会得到什么">
          <div class="proof-heading"><span>一次整理，得到三条可继续使用的路径</span><strong>本地生成 · 用户主动确认</strong></div>
          <div class="proof-flow" aria-hidden="true"><span class="proof-book">微信读书或本地笔记</span><b>→</b><span class="proof-package">压缩包 + ChatGPT 笔记文件</span></div>
          <dl>
            <div><dt>3</dt><dd>连接、上传、演示入口</dd></div>
            <div><dt>4</dt><dd>标记文本兼容格式</dd></div>
            <div><dt>0</dt><dd>默认长期留存</dd></div>
          </dl>
          <p>不会把笔记或提问词放进 ChatGPT 跳转网址；文件由用户本人确认添加。</p>
        </aside>
      </section>

      <section class="workspace-shell" id="export-workspace" aria-labelledby="workspace-title">
        <div class="workspace-heading">
          <div><p class="section-label">三步完成</p><h2 id="workspace-title">选择一种安全的开始方式</h2></div>
          <p>来源可以是演示数据、本人微信读书或本地文件；结果只有在你确认后才下载或打开 ChatGPT。</p>
        </div>

        <ol class="stepper" aria-label="迁移步骤">
          <li class="step is-current" data-step="1" aria-current="step"><span>1</span><div><strong>连接、上传或演示</strong><small>先确认来源与隐私边界</small></div></li>
          <li class="step" data-step="2"><span>2</span><div><strong>选择与配置</strong><small>笔记范围、格式和内容</small></div></li>
          <li class="step" data-step="3"><span>3</span><div><strong>检查并下载</strong><small>压缩包、ChatGPT 文件与跳转</small></div></li>
        </ol>

        <div id="session-banner" class="session-banner hidden" role="status" aria-live="polite">
          <div><strong>一次性会话即将清除</strong><p>为减少敏感数据在浏览器内停留，长时间无操作会自动断开。</p></div>
          <div class="session-actions"><button id="extend-session" class="button compact secondary" type="button">继续 15 分钟</button><button id="expire-session" class="button compact ghost" type="button">现在断开</button></div>
        </div>

        <div class="panels">
          <section class="panel" id="connect-panel" tabindex="-1" aria-labelledby="connect-title">
            <div class="panel-head">
              <div><p class="section-label">步骤一</p><h3 id="connect-title">选择数据来源</h3><p>三种方式共用同一套规范化、导出和校验内核。上传文件与真实密钥不会写入浏览器长期存储、数据库或运维日志。</p></div>
              <span class="status-badge neutral" id="connection-chip">尚未选择</span>
            </div>

            <div class="choice-grid three">
              <article class="choice-card recommended">
                <div class="choice-top"><span class="choice-icon" aria-hidden="true">✦</span><span class="choice-tag">最快体验</span></div>
                <h4>用演示数据体验</h4>
                <p>无需密钥或文件。完整走通选择、整理、压缩包下载与 ChatGPT 继续询问。</p>
                <ul><li>完全虚构的中文演示数据</li><li>不会发出微信读书请求</li><li>会生成真实可校验文件</li></ul>
                <button id="demo-button" class="button primary full" type="button">开始演示</button>
              </article>

              <article class="choice-card upload-choice">
                <div class="choice-top"><span class="choice-icon" aria-hidden="true">⇧</span><span class="choice-tag quiet">本地读取</span></div>
                <h4>上传已有笔记</h4>
                <p>支持一个本工具导出 ZIP、一个规范化 JSON，或一组 Markdown/TXT 文件。文件只在浏览器隔离任务中读取。</p>
                <label id="local-drop" class="file-drop start-upload" for="local-files" tabindex="0">
                  <strong>选择或拖入本地笔记</strong>
                  <span id="local-files-label">ZIP / JSON / Markdown / TXT</span>
                </label>
                <input id="local-files" type="file" accept=".zip,.json,.md,.markdown,.txt,application/zip,application/json,text/markdown,text/plain" multiple hidden />
                <p class="microcopy">文本最多 ${MAX_LOCAL_IMPORT_FILES} 个；单个不超过 ${formatBytes(MAX_LOCAL_IMPORT_FILE_BYTES)}，合计不超过 ${formatBytes(MAX_LOCAL_IMPORT_TOTAL_BYTES)}。</p>
                <button id="local-import-button" class="button secondary full" type="button" disabled>读取所选笔记</button>
              </article>

              <article class="choice-card">
                <div class="choice-top"><span class="choice-icon" aria-hidden="true">⌁</span><span class="choice-tag quiet">连接本人数据</span></div>
                <h4>连接我的微信读书</h4>
                <p>读取你有权访问的个人书架与笔记。本站不提供共享密钥，也不会保存你的密钥。</p>
                <form id="connect-form">
                  <label for="api-key">我的微信读书密钥</label>
                  <div class="key-field"><input id="api-key" name="api-key" type="password" inputmode="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="wrk-…" required /><button id="key-visibility" class="key-addon" type="button" aria-label="显示微信读书密钥" aria-pressed="false">显示</button><button id="key-clear" class="key-addon" type="button">清空</button></div>
                  <button class="button secondary full" type="submit">连接并预览</button>
                </form>
                <p class="microcopy">密钥不进入网址、浏览器长期存储、OVH、私有事实库、R2、OCI、日志或分析系统。</p>
              </article>
            </div>

            <details class="privacy-disclosure"><summary>连接、上传与 ChatGPT 跳转的真实边界</summary><div class="privacy-boundary"><div><strong>会短暂处理</strong><p>本地上传文件只在当前浏览器隔离任务中解析；连接微信读书时，密钥和响应会短暂经过 ChatGPT Sites 同源薄代理与腾讯官方接口网关。</p></div><div><strong>不会自动传输</strong><p>本站不会把笔记放进 ChatGPT 跳转网址，也不会代替用户自动添加附件。结果页只提供安全文件下载、中文提问词和官方 ChatGPT 入口。</p></div></div></details>
            <div class="panel-actions"><button id="disconnect-button" class="button ghost hidden" type="button">断开并清除当前会话</button></div>
          </section>

          <section class="panel hidden" id="select-panel" tabindex="-1" aria-labelledby="select-title">
            <div class="panel-head">
              <div><p class="section-label">步骤二</p><h3 id="select-title">选择要带走的笔记</h3><p>默认全选当前来源。你可以缩小范围，并为目标工具选择明确的兼容格式。</p></div>
              <span class="status-badge success" id="selection-chip">0 项已选</span>
            </div>

            <div id="source-summary" class="source-summary hidden" role="status"></div>
            <div class="toolbar"><label class="search-field"><span class="sr-only">搜索书籍或笔记</span><input id="book-search" type="search" placeholder="搜索书名、文件名或作者" autocomplete="off" /></label><button id="select-filtered" class="button compact secondary" type="button">选择当前结果</button><button id="clear-selection" class="button compact ghost" type="button">清空选择</button></div>
            <div id="book-list" class="book-list" aria-live="polite" aria-label="书籍与笔记列表"></div>

            <div class="configuration">
              <fieldset><legend>标记文本兼容格式</legend><p class="fieldset-help">不同目标使用独立渲染规则，不用一套模板假装全兼容。</p><div class="profile-grid" id="profiles"></div></fieldset>
              <fieldset><legend>导出内容</legend><div class="option-list"><label class="toggle"><input id="offline-search" type="checkbox" checked /><span><strong>离线搜索页</strong><small>解压后即可在本地搜索，不上传笔记。</small></span></label><label class="toggle"><input id="reading-stats" type="checkbox" checked /><span><strong>总体阅读统计</strong><small>仅在当前来源提供时包含。</small></span></label><label class="toggle"><input id="cover-links" type="checkbox" /><span><strong>封面链接</strong><small>仅写入安全链接，不由本站长期保存图片。</small></span></label></div></fieldset>
              <fieldset class="previous"><legend>保护我的手工补充</legend><p class="fieldset-help">可再上传上一次导出的压缩包，保留每本书的“我的永久补充”区域，并生成删除与冲突报告。</p><label class="file-drop" for="previous-zip"><strong>选择上一次导出的压缩包</strong><span id="previous-label">可选，最大 ${formatBytes(MAX_PREVIOUS_ARCHIVE_BYTES)}</span></label><input id="previous-zip" type="file" accept=".zip,application/zip" hidden /></fieldset>
            </div>

            <div class="sticky-summary"><div><strong id="sticky-selection">0 项</strong><span id="sticky-profile">便携纯文本（CommonMark）</span></div><button id="export-button" class="button primary" type="button">检查并生成下载文件</button></div>
          </section>

          <section class="panel hidden" id="result-panel" tabindex="-1" aria-labelledby="result-title">
            <div class="panel-head">
              <div><p class="section-label">步骤三</p><h3 id="result-title">检查结果、下载并继续询问</h3><p>不会自动下载、自动上传到 ChatGPT，也不会把部分失败伪装为完整成功。</p></div>
              <span class="status-badge neutral" id="result-chip">尚未开始</span>
            </div>
            <div id="progress" class="progress-box" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><p>等待开始。</p></div>
            <div id="result-content"></div>
            <div class="panel-actions"><button id="cancel-button" class="button ghost hidden" type="button">取消当前处理</button><button id="restart-button" class="button ghost hidden" type="button">重新开始</button></div>
          </section>
        </div>
        <div id="announce" class="sr-only" aria-live="assertive" aria-atomic="true"></div>
      </section>

      <section class="evidence" id="how" aria-labelledby="evidence-title">
        <div class="evidence-heading"><p class="section-label">为长期可迁移而设计</p><h2 id="evidence-title">上传、下载、追问。<br>每一步都可验证。</h2><p>可靠的迁移不只生成文件，还要说明来源、范围、缺失、兼容格式、校验值，以及如何在不泄露笔记的前提下继续使用。</p></div>
        <div class="evidence-grid">
          <article><span aria-hidden="true">⇧</span><h3>本地上传</h3><p>旧导出 ZIP、规范化 JSON 与 Markdown/TXT 均在浏览器内校验和解析。</p></article>
          <article><span aria-hidden="true">⇩</span><h3>双重下载</h3><p>同时生成完整迁移压缩包，以及适合上传到 ChatGPT 的单文件笔记。</p></article>
          <article><span aria-hidden="true">↗</span><h3>安全跳转</h3><p>只跳转到 ChatGPT 官方入口；笔记和提问词不写入网址，附件由用户主动确认。</p></article>
          <article><span aria-hidden="true">✓</span><h3>证据随包</h3><p>清单、SHA-256、中文导出报告、规范化数据与离线搜索页随包交付。</p></article>
        </div>
      </section>
    </main>

    <footer>
      <div class="footer-brand"><strong>${APP_NAME} ${APP_VERSION}</strong><span>微信读书上游技能版本 ${SOURCE_SKILL_VERSION}</span></div>
      <p>非腾讯、微信读书或 OpenAI 官方产品。只处理当前用户有权访问或主动上传的数据，不提供整书内容导出。</p>
      <div class="footer-links"><a href="/privacy">隐私政策</a><a href="/terms">使用条款</a><a href="/healthz">系统健康</a></div>
    </footer>`;

  const state = {
    worker: undefined,
    connected: false,
    sourceMode: undefined,
    demo: false,
    summaries: [],
    selected: new Set(),
    previousFile: undefined,
    localFiles: [],
    importInfo: undefined,
    busy: false,
    phase: "idle",
    downloadUrl: undefined,
    chatgptDownloadUrl: undefined,
    inactivityWarning: undefined,
    inactivityExpiry: undefined,
    lastResult: undefined,
  };

  const form = $("connect-form");
  const keyInput = $("api-key");
  const demoButton = $("demo-button");
  const importButton = $("local-import-button");
  const localInput = $("local-files");
  const localDrop = $("local-drop");
  const disconnectButton = $("disconnect-button");
  const list = $("book-list");
  const search = $("book-search");
  const profiles = $("profiles");

  for (const [value, label] of Object.entries(PROFILE_LABELS)) {
    const description = profileDescription(value);
    profiles.insertAdjacentHTML(
      "beforeend",
      `<label class="profile-card"><input type="radio" name="profile" value="${value}" ${value === EXPORT_PROFILES.PORTABLE ? "checked" : ""} /><span><strong>${label}</strong><small><b>适合：</b>${description.use}</small><small><b>输出：</b>${description.output}</small></span></label>`,
    );
  }

  $("hero-demo").addEventListener("click", () => connect("demo", ""));
  $("hero-upload").addEventListener("click", focusUpload);
  $("hero-connect").addEventListener("click", focusConnect);
  form.addEventListener("submit", event => {
    event.preventDefault();
    const key = keyInput.value.trim();
    if (!key) {
      keyInput.setAttribute("aria-invalid", "true");
      announce("请输入你自己的微信读书密钥。");
      keyInput.focus();
      return;
    }
    keyInput.removeAttribute("aria-invalid");
    connect("real", key);
    keyInput.value = "";
    keyInput.type = "password";
    updateKeyVisibility(false);
  });
  demoButton.addEventListener("click", () => connect("demo", ""));
  disconnectButton.addEventListener("click", () => disconnect({ focus: true }));
  $("key-visibility").addEventListener("click", () => {
    const showing = keyInput.type === "text";
    keyInput.type = showing ? "password" : "text";
    updateKeyVisibility(!showing);
    keyInput.focus();
  });
  $("key-clear").addEventListener("click", () => {
    keyInput.value = "";
    keyInput.focus();
    announce("微信读书密钥输入框已清空。");
  });
  localInput.addEventListener("change", event => setLocalFiles(event.target.files));
  localDrop.addEventListener("keydown", event => {
    if (["Enter", " "].includes(event.key)) { event.preventDefault(); localInput.click(); }
  });
  for (const eventName of ["dragenter", "dragover"]) localDrop.addEventListener(eventName, event => { event.preventDefault(); localDrop.classList.add("is-dragging"); });
  for (const eventName of ["dragleave", "drop"]) localDrop.addEventListener(eventName, event => { event.preventDefault(); localDrop.classList.remove("is-dragging"); });
  localDrop.addEventListener("drop", event => setLocalFiles(event.dataTransfer?.files));
  importButton.addEventListener("click", startLocalImport);
  search.addEventListener("input", renderBooks);
  $("select-filtered").addEventListener("click", () => {
    for (const summary of filteredBooks()) state.selected.add(summary.bookId);
    renderBooks();
  });
  $("clear-selection").addEventListener("click", () => {
    state.selected.clear();
    renderBooks();
  });
  profiles.addEventListener("change", updateSelection);
  $("previous-zip").addEventListener("change", event => {
    const file = event.target.files?.[0];
    if (file && file.size > MAX_PREVIOUS_ARCHIVE_BYTES) {
      event.target.value = "";
      state.previousFile = undefined;
      $("previous-label").textContent = `文件过大；上限为 ${formatBytes(MAX_PREVIOUS_ARCHIVE_BYTES)}`;
      announce("上一次导出的压缩包超过安全大小上限，未被读取。");
      return;
    }
    state.previousFile = file;
    $("previous-label").textContent = file ? `${file.name} · ${formatBytes(file.size)}` : defaultPreviousLabel();
  });
  $("export-button").addEventListener("click", startExport);
  $("cancel-button").addEventListener("click", () => state.worker?.postMessage({ type: "cancel" }));
  $("restart-button").addEventListener("click", () => disconnect({ focus: true }));
  $("extend-session").addEventListener("click", () => {
    hideSessionWarning();
    resetInactivity();
    announce("一次性会话已延长 15 分钟。");
  });
  $("expire-session").addEventListener("click", () => disconnect({ focus: true }));
  addEventListener("pagehide", () => disconnect(), { once: true });
  for (const eventName of ["pointerdown", "keydown", "focusin"]) addEventListener(eventName, resetInactivity, { passive: true });

  function updateKeyVisibility(showing) {
    const button = $("key-visibility");
    button.textContent = showing ? "隐藏" : "显示";
    button.setAttribute("aria-label", showing ? "隐藏微信读书密钥" : "显示微信读书密钥");
    button.setAttribute("aria-pressed", String(showing));
  }

  function focusConnect() { scrollAndFocus($("connect-panel"), keyInput); }
  function focusUpload() { scrollAndFocus($("connect-panel"), localDrop); }

  function setLocalFiles(fileList) {
    const files = Array.from(fileList ?? []);
    try {
      validateLocalFileDescriptors(files);
      state.localFiles = files;
      const total = files.reduce((sum, file) => sum + file.size, 0);
      const names = files.slice(0, 3).map(file => file.name).join("、");
      $("local-files-label").textContent = `${names}${files.length > 3 ? ` 等 ${files.length} 个文件` : ""} · ${formatBytes(total)}`;
      importButton.disabled = state.busy || !files.length;
      announce(`已选择 ${files.length} 个本地文件，尚未读取。`);
    } catch (error) {
      state.localFiles = [];
      localInput.value = "";
      $("local-files-label").textContent = error.message ?? "所选文件不受支持。";
      importButton.disabled = true;
      announce(error.message ?? "所选文件不受支持。");
    }
  }

  async function startLocalImport() {
    if (!state.localFiles.length || state.busy) return;
    state.phase = "import";
    setBusy(true);
    setStatus($("connection-chip"), "本地校验中", "warning");
    announce("正在浏览器内读取并校验本地笔记，不会上传到服务器。");
    scrollAndFocus($("connect-panel"));
    try {
      const files = [];
      const transfers = [];
      for (const file of state.localFiles) {
        const bytes = await file.arrayBuffer();
        files.push({ name: file.name, type: file.type, size: file.size, bytes });
        transfers.push(bytes);
      }
      ensureWorker().postMessage({ type: "import", files }, transfers);
    } catch {
      fail({ code: "LOCAL_IMPORT", message: "浏览器无法读取所选本地文件。" });
    }
  }

  function ensureWorker() {
    if (state.worker) state.worker.terminate();
    const worker = new Worker(new URL("./export-worker.js", import.meta.url), { type: "module" });
    worker.onmessage = handleWorkerMessage;
    worker.onerror = () => fail({ code: "WORKER", message: "浏览器隔离任务启动失败。" });
    state.worker = worker;
    return worker;
  }

  function connect(mode, key) {
    if (state.busy) return;
    state.phase = "connect";
    setBusy(true);
    setStatus($("connection-chip"), "连接中", "warning");
    announce(mode === "demo" ? "正在载入演示数据。" : "正在连接微信读书并读取书架摘要。");
    scrollAndFocus($("connect-panel"));
    ensureWorker().postMessage({ type: "connect", mode, key });
  }

  function handleWorkerMessage(event) {
    const message = event.data ?? {};
    if (message.type === "progress") {
      if (["connect", "import"].includes(state.phase)) {
        setStatus($("connection-chip"), state.phase === "import" ? "本地读取中" : "读取中", "warning");
        $("connection-chip").title = message.text;
      } else showProgress(message.text);
      return;
    }
    if (message.type === "connected") {
      state.phase = "idle";
      state.connected = true;
      state.sourceMode = message.mode;
      state.demo = message.mode === "demo";
      state.importInfo = message.importInfo;
      state.summaries = message.summaries;
      if (message.mode === "local") {
        state.localFiles = [];
        localInput.value = "";
        importButton.disabled = true;
      }
      state.selected = new Set(message.summaries.map(item => item.bookId));
      const labels = { demo: "演示数据已载入", real: "微信读书已连接", local: "本地笔记已读取" };
      setStatus($("connection-chip"), labels[message.mode] ?? "来源已就绪", "success");
      disconnectButton.classList.remove("hidden");
      $("select-panel").classList.remove("hidden");
      const stats = $("reading-stats");
      stats.disabled = message.mode === "local";
      stats.checked = message.mode !== "local";
      $("source-summary").classList.toggle("hidden", !message.importInfo);
      $("source-summary").innerHTML = message.importInfo
        ? `<strong>已在本地读取：</strong>${escapeHtml(message.importInfo.label)} · ${Number(message.importInfo.bookCount ?? 0)} 个可选条目${message.importInfo.preservesProtectedRegions ? " · 已启用旧包受保护区域" : ""}`
        : "";
      $("previous-label").textContent = defaultPreviousLabel();
      setStep(2);
      renderBooks();
      setBusy(false);
      resetInactivity();
      announce(`已读取 ${message.summaries.length} 个书籍或笔记条目，进入选择与配置。`);
      scrollAndFocus($("select-panel"));
      return;
    }
    if (message.type === "exported") { finishExport(message); return; }
    if (message.type === "disconnected") { setBusy(false); return; }
    if (message.type === "error") fail(message.error);
  }

  function defaultPreviousLabel() {
    if (state.sourceMode === "local" && state.importInfo?.preservesProtectedRegions) return `已自动使用“${state.importInfo.label}”作为保护基线；可在此覆盖`;
    return `可选，最大 ${formatBytes(MAX_PREVIOUS_ARCHIVE_BYTES)}`;
  }

  function filteredBooks() {
    const term = search.value.trim().toLocaleLowerCase("zh-CN");
    return term ? state.summaries.filter(item => `${item.title}\n${item.author}`.toLocaleLowerCase("zh-CN").includes(term)) : state.summaries;
  }

  function renderBooks() {
    const rows = filteredBooks();
    list.innerHTML = rows.length
      ? rows.map(item => {
          const progress = Number.isFinite(Number(item.readingProgress)) ? Math.max(0, Math.min(100, Number(item.readingProgress))) : undefined;
          const local = state.sourceMode === "local";
          return `<label class="book-row"><input type="checkbox" data-book-id="${escapeAttr(item.bookId)}" ${state.selected.has(item.bookId) ? "checked" : ""} /><span class="book-symbol" aria-hidden="true">${escapeHtml((item.title || "记").slice(0, 1))}</span><span class="book-main"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.author || (local ? "本地笔记" : "作者未知"))}</small><span>${item.highlightCount} 划线 · ${item.reviewCount} 想法${local ? "" : ` · ${item.bookmarkCount} 书签`}</span></span><span class="book-count"><b>${item.totalNoteCount}</b><small>条内容</small></span><span class="book-progress"><progress max="100" value="${progress ?? 0}" aria-label="阅读进度 ${progress === undefined ? "未知" : `${progress}%`}"></progress><small>${progress === undefined ? (local ? "本地来源" : "进度未知") : `已读 ${progress}%`}</small></span></label>`;
        }).join("")
      : `<p class="empty-state">没有匹配的书籍或笔记。</p>`;
    for (const checkbox of list.querySelectorAll("input[data-book-id]")) {
      checkbox.addEventListener("change", () => {
        checkbox.checked ? state.selected.add(checkbox.dataset.bookId) : state.selected.delete(checkbox.dataset.bookId);
        updateSelection();
      });
    }
    updateSelection();
  }

  function updateSelection() {
    const profile = document.querySelector('input[name="profile"]:checked')?.value ?? EXPORT_PROFILES.PORTABLE;
    const count = state.selected.size;
    $("selection-chip").textContent = `${count} 项已选`;
    $("sticky-selection").textContent = `${count} 项`;
    $("sticky-profile").textContent = PROFILE_LABELS[profile] ?? profile;
    $("export-button").disabled = !count || state.busy;
  }

  async function startExport() {
    if (!state.connected || !state.selected.size || state.busy) return;
    const profile = document.querySelector('input[name="profile"]:checked')?.value ?? EXPORT_PROFILES.PORTABLE;
    let previousZip;
    try {
      if (state.previousFile) {
        if (state.previousFile.size > MAX_PREVIOUS_ARCHIVE_BYTES) throw new Error("archive too large");
        previousZip = await state.previousFile.arrayBuffer();
      }
    } catch {
      fail({ code: "PREVIOUS_EXPORT", message: "无法读取上一次导出的压缩包，或文件超过安全上限。" });
      return;
    }
    state.phase = "export";
    setBusy(true, "正在整理选中笔记…");
    $("result-panel").classList.remove("hidden");
    $("cancel-button").classList.remove("hidden");
    $("restart-button").classList.add("hidden");
    $("result-content").innerHTML = "";
    setStatus($("result-chip"), "生成中", "warning");
    setStep(3);
    announce("开始生成下载文件。");
    scrollAndFocus($("result-panel"));
    const message = {
      type: "export",
      selectedIds: Array.from(state.selected),
      profile,
      includeOfflineSearch: $("offline-search").checked,
      includeReadingStatistics: $("reading-stats").checked,
      includeCover: $("cover-links").checked,
      previousZip,
    };
    state.worker.postMessage(message, previousZip ? [previousZip] : []);
  }

  function finishExport(message) {
    state.phase = "idle";
    revokeDownloads();
    const zipBlob = new Blob([message.bytes], { type: "application/zip" });
    const hasChatgpt = Boolean(message.chatgpt?.bytes && message.chatgpt?.filename && message.chatgpt?.prompt);
    const chatgptBlob = hasChatgpt ? new Blob([message.chatgpt.bytes], { type: "text/markdown;charset=utf-8" }) : undefined;
    state.downloadUrl = URL.createObjectURL(zipBlob);
    state.chatgptDownloadUrl = chatgptBlob ? URL.createObjectURL(chatgptBlob) : undefined;
    state.lastResult = { ...message, zipBlob, chatgptBlob };
    const complete = message.status === "COMPLETE";
    const statusLabel = complete ? "完整导出" : "部分导出";
    setStatus($("result-chip"), statusLabel, complete ? "success" : "warning");
    $("progress").classList.add("hidden");
    $("cancel-button").classList.add("hidden");
    $("restart-button").classList.remove("hidden");
    const updated = Number(message.manifest.updatedBookCount ?? message.manifest.bookCount ?? 0);
    const retained = Number(message.manifest.retainedBookCount ?? 0);
    const tombstones = Number(message.manifest.tombstoneCount ?? 0);
    const failures = Number(message.manifest.failureCount ?? 0);
    const hash = String(message.manifest.canonicalSha256 ?? "");
    const outcomeCopy = complete
      ? "所有已选内容均已生成。下载前请核对文件名、大小与校验值。"
      : "有部分内容未能读取或生成。压缩包会保留成功结果，并在《导出报告》中逐项说明失败。";
    const chatgptSection = hasChatgpt ? `
      <section class="chatgpt-card" aria-labelledby="chatgpt-title">
        <div class="chatgpt-heading"><span class="chatgpt-mark" aria-hidden="true">问</span><div><p class="download-label">继续使用</p><h4 id="chatgpt-title">把笔记带到你自己的 ChatGPT</h4></div></div>
        <p>先下载专用 Markdown 文件，再打开 ChatGPT 并由你本人添加附件。本站不会把笔记或提问词写进跳转网址，也不会声称已经替你自动上传。</p>
        <div class="chatgpt-file"><div><span>专用笔记文件</span><strong>${escapeHtml(message.chatgpt.filename)}</strong><code>SHA-256：${escapeHtml(message.chatgpt.sha256)}</code></div><a id="download-chatgpt" class="button secondary" download="${escapeAttr(message.chatgpt.filename)}" href="${state.chatgptDownloadUrl}">下载供 ChatGPT 读取的笔记</a></div>
        <div class="chatgpt-actions"><button id="copy-chatgpt-prompt" class="button secondary" type="button">复制中文提问词</button><button id="copy-open-chatgpt" class="button primary" type="button">复制提问词并打开 ChatGPT</button><a id="open-chatgpt" class="button ghost" href="${CHATGPT_HANDOFF_URL}" target="_blank" rel="noopener noreferrer">只打开 ChatGPT</a></div>
        <details class="prompt-preview"><summary>查看或手动复制提问词</summary><textarea id="chatgpt-prompt" readonly rows="10">${escapeHtml(message.chatgpt.prompt)}</textarea></details>
      </section>` : `
      <section class="chatgpt-card" aria-labelledby="chatgpt-title">
        <div class="chatgpt-heading"><span class="chatgpt-mark" aria-hidden="true">!</span><div><p class="download-label">安全降级</p><h4 id="chatgpt-title">本次未生成 ChatGPT 专用笔记</h4></div></div>
        <p>${escapeHtml(message.manifest.chatgptHandoff?.message ?? "专用笔记触发了容量或敏感内容安全边界。完整迁移压缩包仍可下载，请查看其中的《导出报告》。")}</p>
        <div class="chatgpt-actions"><a id="open-chatgpt" class="button ghost" href="${CHATGPT_HANDOFF_URL}" target="_blank" rel="noopener noreferrer">只打开 ChatGPT</a></div>
      </section>`;
    $("result-content").innerHTML = `
      <div class="outcome-card ${complete ? "complete" : "partial"}">
        <div class="outcome-icon" aria-hidden="true">${complete ? "✓" : "!"}</div>
        <div><p class="outcome-label">${statusLabel}</p><h4>${complete ? "下载文件已准备好" : "请先确认缺失项"}</h4><p>${outcomeCopy}</p></div>
      </div>
      <dl class="result-metrics">
        <div><dt>本次更新</dt><dd>${updated} 项</dd></div><div><dt>从旧包保留</dt><dd>${retained} 项</dd></div><div><dt>非破坏归档</dt><dd>${tombstones} 项</dd></div><div><dt>失败项</dt><dd>${failures}</dd></div><div><dt>压缩包大小</dt><dd>${formatBytes(zipBlob.size)}</dd></div>
      </dl>
      <div class="download-card">
        <div><span class="download-label">完整迁移压缩包</span><strong>${escapeHtml(message.filename)}</strong></div>
        <div class="hash-row"><code>${escapeHtml(hash)}</code><button id="copy-hash" class="button compact ghost" type="button">复制 SHA-256</button></div>
        <a class="button ${complete ? "primary" : "warning"} full download" download="${escapeAttr(message.filename)}" href="${state.downloadUrl}">${complete ? "下载完整迁移压缩包" : "下载部分结果压缩包"}</a>
      </div>
      ${chatgptSection}
      <p class="result-help">完整压缩包内含中文标记文本、规范化数据、离线搜索、ChatGPT 使用说明、文件清单和导出报告。下一次可上传本压缩包，保护手工补充并避免内容被静默丢失。</p>`;

    $("copy-hash").addEventListener("click", event => copyWithFeedback(hash, event.currentTarget, "SHA-256 已复制到剪贴板。"));
    if (hasChatgpt) {
      $("copy-chatgpt-prompt").addEventListener("click", event => copyWithFeedback(message.chatgpt.prompt, event.currentTarget, "ChatGPT 中文提问词已复制。"));
      $("copy-open-chatgpt").addEventListener("click", event => {
        window.open(CHATGPT_HANDOFF_URL, "_blank", "noopener,noreferrer");
        copyWithFeedback(message.chatgpt.prompt, event.currentTarget, "已请求打开 ChatGPT；如浏览器拦截新窗口，请点击“只打开 ChatGPT”。请在新页面添加刚下载的 Markdown 文件。");
      });
    }
    setBusy(false);
    resetInactivity();
    announce(hasChatgpt
      ? `${statusLabel}。压缩包和 ChatGPT 笔记文件已准备好，均需你主动下载。`
      : `${statusLabel}。迁移压缩包已准备好；ChatGPT 专用笔记因安全边界未生成。`);
    scrollAndFocus($("result-panel"), $("result-content").querySelector("a.download"));
  }

  async function copyWithFeedback(text, button, successMessage) {
    try {
      await navigator.clipboard.writeText(text);
      const previous = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(() => { if (button.isConnected) button.textContent = previous; }, 1_800);
      announce(successMessage);
    } catch {
      const area = $("chatgpt-prompt");
      if (area && text === state.lastResult?.chatgpt?.prompt) { area.focus(); area.select(); }
      button.textContent = "请手动复制";
      announce("浏览器未允许自动复制，已定位到可手动复制的内容。");
    }
  }

  function fail(error) {
    const wasStarting = ["connect", "import"].includes(state.phase);
    state.phase = "idle";
    setBusy(false);
    if (wasStarting) setStatus($("connection-chip"), "读取失败", "danger");
    $("cancel-button").classList.add("hidden");
    $("restart-button").classList.remove("hidden");
    $("result-panel").classList.remove("hidden");
    $("progress").classList.add("hidden");
    setStatus($("result-chip"), "未完成", "danger");
    $("result-content").innerHTML = `<div class="outcome-card failed" role="alert"><div class="outcome-icon" aria-hidden="true">×</div><div><p class="outcome-label">${escapeHtml(errorCodeLabel(error.code))}</p><h4>没有生成可下载的成功结果</h4><p>${escapeHtml(error.message ?? "操作失败。")}</p><div class="inline-actions"><button id="error-demo" class="button secondary" type="button">改用演示数据</button><button id="error-upload" class="button ghost" type="button">重新上传</button><button id="error-connect" class="button ghost" type="button">重新连接</button></div></div></div>`;
    $("error-demo").addEventListener("click", () => connect("demo", ""));
    $("error-upload").addEventListener("click", focusUpload);
    $("error-connect").addEventListener("click", focusConnect);
    setStep(3);
    announce(`操作失败：${error.message ?? "未知错误"}`);
    scrollAndFocus($("result-panel"), $("error-demo"));
  }

  function showProgress(text) {
    $("result-panel").classList.remove("hidden");
    $("progress").classList.remove("hidden");
    $("progress").innerHTML = `<span class="spinner" aria-hidden="true"></span><p>${escapeHtml(text)}</p>`;
  }

  function setBusy(value, text) {
    state.busy = value;
    form.querySelector('button[type="submit"]').disabled = value;
    demoButton.disabled = value;
    importButton.disabled = value || !state.localFiles.length;
    $("hero-demo").disabled = value;
    $("hero-upload").disabled = value;
    $("hero-connect").disabled = value;
    $("export-button").disabled = value || !state.selected.size;
    if (text && state.phase === "export") showProgress(text);
  }

  function revokeDownloads() {
    if (state.downloadUrl) URL.revokeObjectURL(state.downloadUrl);
    if (state.chatgptDownloadUrl) URL.revokeObjectURL(state.chatgptDownloadUrl);
    state.downloadUrl = undefined;
    state.chatgptDownloadUrl = undefined;
  }

  function disconnect({ focus = false } = {}) {
    clearTimeout(state.inactivityWarning);
    clearTimeout(state.inactivityExpiry);
    hideSessionWarning();
    revokeDownloads();
    state.worker?.postMessage({ type: "disconnect" });
    state.worker?.terminate();
    state.worker = undefined;
    state.phase = "idle";
    state.connected = false;
    state.sourceMode = undefined;
    state.demo = false;
    state.summaries = [];
    state.selected.clear();
    state.previousFile = undefined;
    state.localFiles = [];
    state.importInfo = undefined;
    state.lastResult = undefined;
    keyInput.value = "";
    keyInput.type = "password";
    updateKeyVisibility(false);
    localInput.value = "";
    $("local-files-label").textContent = "ZIP / JSON / Markdown / TXT";
    $("previous-zip").value = "";
    $("previous-label").textContent = defaultPreviousLabel();
    $("source-summary").classList.add("hidden");
    $("reading-stats").disabled = false;
    $("reading-stats").checked = true;
    setStatus($("connection-chip"), "尚未选择", "neutral");
    disconnectButton.classList.add("hidden");
    $("select-panel").classList.add("hidden");
    $("result-panel").classList.add("hidden");
    $("restart-button").classList.add("hidden");
    setStep(1);
    setBusy(false);
    if (focus) {
      announce("当前会话、密钥和本地上传内容已从浏览器隔离任务中清除。");
      scrollAndFocus($("connect-panel"), demoButton);
    }
  }

  function resetInactivity() {
    if (!state.connected) return;
    clearTimeout(state.inactivityWarning);
    clearTimeout(state.inactivityExpiry);
    hideSessionWarning();
    state.inactivityWarning = setTimeout(() => {
      $("session-banner").classList.remove("hidden");
      announce("一次性会话将在两分钟后自动清除。你可以延长会话或现在断开。");
    }, 13 * 60_000);
    state.inactivityExpiry = setTimeout(() => {
      disconnect({ focus: true });
      announce("一次性会话已因长时间无操作而自动清除，请重新选择来源。");
    }, 15 * 60_000);
  }

  function hideSessionWarning() { $("session-banner").classList.add("hidden"); }

  function setStep(number) {
    for (const item of document.querySelectorAll(".step")) {
      const current = Number(item.dataset.step) === number;
      item.classList.toggle("is-current", current);
      if (current) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    }
  }

  function announce(text) {
    const region = $("announce");
    region.textContent = "";
    requestAnimationFrame(() => { region.textContent = text; });
  }
}

function renderLegal(kind) {
  const privacy = kind === "privacy";
  app.innerHTML = `<a class="skip-link" href="#legal-content">跳到正文</a><header class="topbar"><a class="brand" href="/"><span class="brand-mark" aria-hidden="true">阅</span><span class="brand-copy"><strong>${APP_NAME}</strong><small>上传、整理、下载并继续询问</small></span></a><nav aria-label="站点导航"><a href="/">返回迁移工具</a></nav></header><main class="legal" id="legal-content"><p class="section-label">${privacy ? "隐私说明" : "使用边界"}</p><h1>${privacy ? "隐私政策" : "使用条款"}</h1>${privacy ? privacyText() : termsText()}<p class="legal-version">版本 ${APP_VERSION} · 2026-07-26</p></main>`;
}

function privacyText() {
  return `<h2>核心承诺</h2><p>${APP_NAME}的公开首版服务不主动持久化微信读书密钥、上传文件、原始接口响应、书名、划线、想法、点评、搜索词或生成的下载文件。</p><h2>本地上传</h2><p>你主动选择的 ZIP、JSON、Markdown 或 TXT 文件只在当前浏览器隔离任务中解析。应用不会把上传文件发送到 OVH、私有事实库、R2、OCI、日志或分析系统。</p><h2>连接微信读书</h2><p>当你主动连接时，密钥会在当前浏览器隔离任务和同源服务器薄代理的单次请求内存中短暂处理，再转发到腾讯公开的微信读书智能接口网关。标记文本、结构化数据、离线搜索和压缩包在浏览器内生成。</p><h2>继续使用 ChatGPT</h2><p>结果页会生成一份适合上传到 ChatGPT 的 Markdown 文件、中文提问词和指向 ${CHATGPT_HANDOFF_URL} 的固定官方入口。本站不会把笔记、密钥或提问词放入跳转网址，也不会代表你自动添加附件；文件必须由你本人在自己的 ChatGPT 会话或项目中确认添加。</p><h2>统计与清除</h2><p>匿名使用不要求登录。ChatGPT Sites 可提供站点级访问统计，应用不把密钥、文件名、书名、搜索词或笔记内容发送给统计系统。关闭页面、点击“断开并清除当前会话”或 15 分钟无操作后，浏览器会终止隔离任务。</p>`;
}

function termsText() {
  return `<h2>允许用途</h2><p>你只能处理自己有权访问的微信读书个人数据，或自己有权使用的本地笔记文件，并自行保管密钥与下载结果。</p><h2>禁止用途</h2><ul><li>不得共享、收集、猜测或滥用他人的微信读书密钥。</li><li>不得通过本工具抓取、破解、分发整本受版权保护的书籍内容。</li><li>不得上传恶意归档、实施自动化滥用或造成异常负载。</li><li>不得把跳转到 ChatGPT 理解为本站、OpenAI 或腾讯已经替你审核、保存或背书笔记内容。</li></ul><h2>服务边界</h2><p>本工具与腾讯、微信、微信读书或 OpenAI 无隶属、授权、背书或代理关系。上游接口与 ChatGPT Sites 托管能力可能变化；系统遇到上游升级指令、凭证失败、文件完整性失败或数据冲突时会安全停止受影响操作。</p><h2>数据责任</h2><p>结果可能因上游字段、权限、上传文件质量或临时故障而不完整。请查看压缩包内的《导出报告》和文件清单；“部分完成”不能当作完整备份。</p>`;
}

function profileDescription(value) {
  return ({
    [EXPORT_PROFILES.PORTABLE]: { use: "跨编辑器长期保存", output: "最少扩展、稳定标题与链接" },
    [EXPORT_PROFILES.GFM]: { use: "GitHub 及同类代码仓库编辑器", output: "表格、任务列表与仓库预览优化" },
    [EXPORT_PROFILES.OBSIDIAN]: { use: "Obsidian 双链笔记库", output: "YAML 元数据、提示块与内部链接结构" },
    [EXPORT_PROFILES.NOTION]: { use: "Notion 压缩包导入", output: "避免页首元数据块，降低导入损失" },
  })[value] ?? { use: "通用", output: "标准标记文本" };
}

function scrollAndFocus(container, target = container) {
  container.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  window.setTimeout(() => target?.focus({ preventScroll: true }), prefersReducedMotion() ? 0 : 180);
}

function prefersReducedMotion() { return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false; }
function setStatus(element, text, tone) { element.textContent = text; element.className = `status-badge ${tone}`; }
function $(id) { return document.getElementById(id); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }
function formatBytes(bytes) { if (bytes < 1024) return `${bytes} 字节`; if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} 千字节`; return `${(bytes / 1024 ** 2).toFixed(1)} 兆字节`; }
function errorCodeLabel(code) { return ({ AUTH: "身份凭证无效", FORBIDDEN: "请求被拒绝", RATE_LIMIT: "请求过于频繁", TIMEOUT: "上游响应超时", NETWORK: "网络连接失败", UPSTREAM: "上游服务异常", SCHEMA: "上游数据格式变化", UPGRADE_REQUIRED: "上游协议需要升级", BLOCKED_UPGRADE: "上游协议需要升级", PREVIOUS_EXPORT: "旧导出包无效", LOCAL_IMPORT: "本地文件无法读取", ARCHIVE: "压缩包无效", CANCELLED: "操作已取消", WORKER: "浏览器隔离任务异常", INVALID_REQUEST: "请求参数无效", NO_EXPORTABLE_DATA: "没有可导出的内容", TOO_LARGE: "数据超过安全上限" }[String(code ?? "")] ?? "操作错误"); }
