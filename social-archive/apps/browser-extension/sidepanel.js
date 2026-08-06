/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const running = new Set(["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"]);
  const needsAction = new Set(["partial", "failed", "blocked_environment"]);
  const icons = { xiaohongshu: "小", douyin: "抖", kuaishou: "快", bilibili: "B", x: "X", reddit: "R", instagram: "In", youtube: "Y", "generic-web": "书" };
  // **平台中文名走目录，不在这里再写一份。**
  // 仓里已经有四份（服务端、扩展目录、设置页、资料库）——改一个名字要记得改
  // 五处，漏一处就有一个界面显示原始 id。图标留在本地：目录里没有图标，
  // 那本来就该各页自己定。
  const platformName = platform => platform === "generic-web"
    ? "Chrome书签/网页"
    : (globalThis.SAPlatformCatalog?.platformLabel?.(platform) || platform);
  let accounts = [];
  let runs = [];
  let filter = "active";
  let timer = null;

  function label(status) {
    return ({ queued: "等待同步", authorizing: "正在授权", discovering: "正在发现", scanning: "正在同步", normalizing: "正在整理", artifacting: "正在归档", exporting: "正在导出", completed: "已完成", partial: "部分完成", paused: "已暂停", failed: "需要处理", blocked_environment: "重新连接", cancelled: "已取消" })[status] || status;
  }
  function showBanner(message) { $("banner").textContent = message; $("banner").classList.remove("hidden"); }
  function visible() {
    if (filter === "all") return runs;
    if (filter === "needs") return runs.filter(run => needsAction.has(run.status));
    return runs.filter(run => running.has(run.status) || run.status === "paused");
  }
  async function openLibrary() { chrome.tabs.create({ url: (await SA.getConfig()).libraryUrl }); }

  async function control(run, action, button) {
    if (action === "cancel" && !confirm("取消本次同步？已经导入的内容会保留。")) return;
    button.disabled = true;
    try {
      const result = await chrome.runtime.sendMessage({ type: "SA_CONTROL_SYNC_RUN", syncRunId: run.id, accountId: run.source_account_id, action });
      if (!result?.ok) throw new Error(result?.error || result?.message || "操作失败");
      await refresh();
    } catch (error) {
      showBanner(error?.message || "无法控制同步任务");
    } finally { button.disabled = false; }
  }

  function bindControl(card, selector, run, action, visibleWhen) {
    const button = card.querySelector(selector);
    button.classList.toggle("hidden", !visibleWhen);
    if (visibleWhen) button.addEventListener("click", () => control(run, action, button));
  }

  function render() {
    const states = runs.map(run => run.status);
    $("activeCount").textContent = states.filter(status => running.has(status) || status === "paused").length;
    $("doneCount").textContent = states.filter(status => status === "completed").length;
    $("actionCount").textContent = states.filter(status => needsAction.has(status)).length;
    const list = visible();
    $("empty").classList.toggle("hidden", list.length > 0);
    // **空状态要照实际情况说话。**
    //
    // 写死的那两句是「没有需要处理的同步 / 连接账号后…会显示在这里」。
    // 而他刚连完账号、刚同步完一次，打开这一页看到的就是这两句——
    // 上面明明写着「1 已完成」，下面却在教他去连接账号。
    // 实测（2026-08-06 真 Chrome）：0 同步中 / 1 已完成 / 0 需处理，列表空、
    // 空状态照旧那两句。**默认筛选是「同步中」，空是对的，说的话不对。**
    if (list.length === 0) {
      const done = Number($("doneCount").textContent || 0);
      const everRan = runs.length > 0;
      $("emptyTitle").textContent = everRan ? "现在没有正在跑的同步" : "还没有同步过";
      $("emptyCopy").textContent = everRan
        ? `最近${done ? `完成了 ${done} 次` : "的同步"}——点上面的「全部」可以看。`
        : "连接账号后，首次全量和后续增量同步会显示在这里。";
    }
    $("list").replaceChildren();
    for (const run of list) {
      const account = accounts.find(item => item.id === run.source_account_id) || {};
      const fragment = $("cardTemplate").content.cloneNode(true);
      const card = fragment.querySelector(".card");
      card.classList.add(run.status);
      card.querySelector(".platform").textContent = icons[run.platform] || "网";
      card.querySelector(".title strong").textContent = account.display_name || platformName(run.platform) || run.platform;
      card.querySelector(".title small").textContent = `${run.mode === "first_full" ? "首次全量" : "增量同步"} · ${Number(run.imported_count || 0).toLocaleString("zh-CN")}/${Number(run.discovered_count || 0) || "…"} 条`;
      card.querySelector(".status").textContent = label(run.status);
      const progress = run.discovered_count ? Math.min(100, Math.round(Number(run.imported_count || 0) / Number(run.discovered_count) * 100)) : (run.status === "completed" ? 100 : 18);
      card.querySelector(".progress span").style.width = `${progress}%`;
      // 失败时显示服务端算好的冻结词典句子（v0.0.0.7 / T14）。
      //
      // **刻意不再显示 run.last_error_message**：那是上游原样抛回来的错误文本，
      // 可能是英文、可能是一大坨 CSS——Reddit 未授权时 gallery-dl 塞回来的
      // 就是十万字节的样式表（见 evidence/fixtures/gallerydl/）。
      // T14 的硬规矩：界面上不得出现英文错误码或堆栈，给人看的永远是中文句子。
      // 原始文本仍在库里，供日志与排查用，只是不往界面上放。
      card.querySelector(".message").textContent = run.message_zh || (run.status === "completed" ? "内容已进入资料库并继续后台导出。" : running.has(run.status) ? "已完成内容会立即显示；可以随时暂停或取消。" : run.status === "paused" ? "同步已暂停；点击继续会从现有进度恢复。" : "点击重试或重新连接账号。");

      bindControl(card, ".pause", run, "pause", running.has(run.status));
      bindControl(card, ".resume", run, "resume", run.status === "paused");
      bindControl(card, ".retry", run, "retry", ["partial", "failed"].includes(run.status));
      bindControl(card, ".cancel", run, "cancel", running.has(run.status) || run.status === "paused");
      card.querySelector(".details").addEventListener("click", openLibrary);
      $("list").appendChild(fragment);
    }
  }

  async function showLocalFailureIfServerNeverHeardAboutIt() {
    // 有一种失败**服务端根本不知道**：同步还没拿到 syncRunId 就被放弃了
    // （MV3 的 worker 反复被杀，attempts 到顶）。那时唯一的记录是扩展本地的
    // saAccountSyncQueueLastResult。
    //
    // 这个键此前**写了三处、读零处** —— 我当初为「放弃时也要说得出原因」
    // 补的那条记录，写进了没人看的地方。写进没人读的地方，和没写是一回事，
    // 但它看起来像写了。（scripts/find_write_only_storage_keys.py 扫出来的。）
    try {
      const stored = await chrome.storage.local.get({ saAccountSyncQueueLastResult: null });
      const last = stored.saAccountSyncQueueLastResult;
      if (!last || last.ok !== false) return;
      // 服务端已经知道这次失败了，就别重复说
      if (last.syncRunId && runs.some(run => run.id === last.syncRunId)) return;
      showBanner(last.error || "上一次同步没有跑完。");
    } catch (_) {
      // 读不到本地记录不该影响主渲染——它是补充信息
    }
  }

  async function refresh() {
    try {
      const [accountResponse, runResponse] = await Promise.all([
        SA.api("/v1/accounts", { timeoutMs: 7000 }),
        SA.api("/v1/sync-runs?limit=200", { timeoutMs: 7000 })
      ]);
      accounts = accountResponse.items || [];
      runs = runResponse.items || [];
      $("banner").classList.add("hidden");
      render();
      await showLocalFailureIfServerNeverHeardAboutIt();
    } catch (error) {
      accounts = [];
      runs = [];
      render();
      showBanner(`尚未连接私人档案馆：${error?.message || "请完成设置"}`);
    }
  }

  $("refresh").addEventListener("click", refresh);
  $("syncAll").addEventListener("click", async () => {
    $("syncAll").disabled = true;
    try {
      const result = await chrome.runtime.sendMessage({ type: "SA_SYNC_ALL_ACCOUNTS" });
      if (!result?.ok) throw new Error("请先连接账号");
      await refresh();
    } catch (error) { showBanner(error?.message || "无法同步账号"); }
    finally { $("syncAll").disabled = false; }
  });
  $("connectAccount").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" }));
  $("openLibrary").addEventListener("click", openLibrary);
  $("openSettings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => {
    filter = button.dataset.filter;
    document.querySelector("[data-filter].active")?.classList.remove("active");
    button.classList.add("active");
    render();
  }));
  refresh();
  timer = setInterval(refresh, 5000);
  addEventListener("unload", () => clearInterval(timer));
})();
