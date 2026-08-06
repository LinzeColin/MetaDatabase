/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const platformShort = { xiaohongshu: "小", douyin: "抖", kuaishou: "快", bilibili: "B", x: "X", reddit: "R", instagram: "In", youtube: "Y", "generic-web": "网" };
  // **平台中文名走目录，不在这里再写一份。**
  // 仓里已经有四份（服务端、扩展目录、设置页、资料库）；每多一份，
  // 改一个名字就要多记一处，漏掉的那处会显示原始 id。
  const platformName = new Proxy({}, { get: (_, key) => String(key) === "generic-web"
    ? "Chrome 书签 / 网页"
    : (globalThis.SAPlatformCatalog?.platformLabel?.(String(key)) || String(key)) });
  const statusName = { connected: "已连接", degraded: "降级可用", completed: "同步完成", partial: "部分完成", queued: "等待同步", discovering: "正在发现", scanning: "同步中", normalizing: "正在整理", artifacting: "正在归档", exporting: "正在导出", failed: "需要处理", blocked_environment: "重新连接", paused: "已暂停" };

  let config = null;
  let tab = null;
  let platform = null;
  let accounts = [];
  let platformSupport = {};
  let workerState = null;
  let runs = [];
  let bootstrap = null;

  function showStatus(text, type = "success") {
    const element = $("status");
    element.textContent = text;
    element.className = `status ${type === "success" ? "" : type}`.trim();
  }
  function setBusy(value) {
    $("primarySync").disabled = value;
    $("manageAccounts").disabled = value;
    $("savePage").disabled = value;
  }
  function latestRun(accountId) {
    return runs.filter(run => run.source_account_id === accountId).sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0] || null;
  }
  function formatTime(value) {
    if (!value) return "尚未同步";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "尚未同步";
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date).replaceAll("/", "-");
  }

  async function renderAuthorization() {
    const permission = await SA.permissionState(platform.id);
    if (permission.authorized) {
      $("authorization").innerHTML = '<span class="auth-pill connected">当前站点已授权</span>';
      return;
    }
    $("authorization").innerHTML = '<button id="authorizeSite" class="authorize-button">授权当前站点</button>';
    $("authorizeSite").addEventListener("click", async () => {
      const granted = await SA.requestPlatformPermission(platform.id);
      if (!granted) return showStatus("未获得站点授权。账号批量同步不会因此被标记成功。", "needs");
      await renderAuthorization();
      showStatus("当前站点已授权。单条保存现在可用。");
    });
  }

  function renderSummary(serviceConnected) {
    const connected = accounts.filter(account => ["connected", "degraded"].includes(account.connection_state)).length;
    const active = runs.filter(run => ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(run.status));
    const total = accounts.reduce((sum, account) => sum + Number(account.content_count || 0), 0);
    // 后台没在跑要单独说一句——它和「连不上」不是一回事：
    // 连不上是他这边的配置问题，后台没跑是服务器那边的事，
    // 而两者的表现（同步永远不完成）一模一样。分开说他才知道该找谁。
    const workerDown = Boolean(workerState && workerState.ever_seen
                               && workerState.alive === false);
    $("serviceState").className = `service-pill ${
      !serviceConnected ? "error" : workerDown ? "needs" : "connected"}`;
    $("serviceState").textContent = !serviceConnected ? "待连接"
      : workerDown ? "后台没在跑" : "已连接";
    if (!serviceConnected) {
      $("summaryTitle").textContent = "私人档案馆尚未连接";
      $("summaryCopy").textContent = "打开设置完成一次配对。";
      $("primarySyncLabel").textContent = "连接私人档案馆";
      $("primarySyncHint").textContent = "完成后才能同步账号收藏";
      return;
    }
    if (!connected) {
      $("summaryTitle").textContent = "还没有连接平台账号";
      $("summaryCopy").textContent = "连接一次账号后自动全量导入，不需要逐条点击。";
      $("primarySyncLabel").textContent = "连接第一个账号";
      // **写死的数会漂。** 这里原来写「支持 8 个平台与 Chrome 书签」——
      // 加一个平台就错一次，而且「支持」在这一屏读起来像「能自动同步」，
      // 实际那个数是"可保存的平台数"。改成按能力声明现算，并说清是哪一种。
      {
        const syncable = Object.values(platformSupport)
          .filter(item => item?.sync_supported !== false).length;
        $("primarySyncHint").textContent = syncable
          ? `本版本有 ${syncable} 个来源能自动同步`
          : "本版本还没有能自动同步的来源";
      }
      return;
    }
    $("summaryTitle").textContent = `${connected} 个账号 · ${total.toLocaleString("zh-CN")} 条内容`;
    if (active.length) {
      const imported = active.reduce((sum, run) => sum + Number(run.imported_count || 0), 0);
      const discovered = active.reduce((sum, run) => sum + Number(run.discovered_count || 0), 0);
      $("summaryCopy").textContent = `${active.length} 个同步任务正在运行 · ${imported}/${discovered || "…"} 条`;
      $("primarySyncLabel").textContent = "查看同步进度";
      $("primarySyncHint").textContent = "已完成内容会立即出现在资料库";
    } else {
      // **别承诺点赞。** 这句原来写「只同步新增收藏、点赞和书签」，
      // 而 SCANNABLE_RELATIONS 里一个平台都没有点赞——那条取数路没做。
      // 承诺一件不会发生的事，比不提更糟：他会以为点赞丢了。
      $("summaryCopy").textContent = "首次全量之后，只同步新增的那些。";
      $("primarySyncLabel").textContent = "立即同步全部账号";
      $("primarySyncHint").textContent = "无需逐条打开帖子";
    }
  }

  function renderAccounts() {
    if (!accounts.length) {
      $("accountList").innerHTML = '<div class="empty-accounts">没有已连接账号。点击上方“连接与管理账号”开始。</div>';
      return;
    }
    $("accountList").innerHTML = accounts.slice(0, 5).map(account => {
      const run = latestRun(account.id);
      const current = run?.status || account.connection_state || "connected";
      const imported = Number(run?.imported_count || 0);
      const discovered = Number(run?.discovered_count || 0);
      const detail = ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(current)
        ? `同步 ${imported}/${discovered || "…"}`
        : `${Number(account.content_count || 0).toLocaleString("zh-CN")} 条 · ${formatTime(account.last_sync_at)}`;
      return `<article class="account-row"><span class="platform-dot">${SA.escapeHtml(platformShort[account.platform] || "网")}</span><span class="account-copy"><strong>${SA.escapeHtml(account.display_name || account.external_account_id || platformName[account.platform] || account.platform)}</strong><small>${SA.escapeHtml(detail)}</small></span><span class="state-label ${SA.escapeHtml(current)}">${SA.escapeHtml(statusName[current] || current)}</span></article>`;
    }).join("");
  }

  function renderDestinations() {
    const items = bootstrap?.destinations || [];
    const map = new Map(items.map(item => [item.destination_id, item]));
    const ids = ["markdown", "notion", "obsidian", "github"];
    $("destinationChips").innerHTML = ids.map(id => {
      const item = map.get(id) || {};
      const state = id === "markdown" ? "connected" : (item.state || "needs_user_action");
      return `<span class="destination-chip ${SA.escapeHtml(state)}"><span class="destination-dot"></span>${SA.escapeHtml(SA.destinationLabel(id))} · ${SA.escapeHtml(SA.statusCopy(state))}</span>`;
    }).join("");
  }

  /** 把弹窗里三句会漂的话，照服务端的事实清单重写（v0.0.0.14）。
   *
   * 这三句说的都是同一件事：「哪些平台能自动同步」。
   * 写死的后果已经发生过——B 站接上两个版本之后，诊断面板还在说它读不了。
   *
   * **读不到就不动写死的那份**：服务不可达时保持原样，
   * 总比把它清成空白强。
   */
  function renderPlatformCopy() {
    const support = Object.values(platformSupport);
    if (!support.length) return;
    const names = Object.fromEntries((SA.PLATFORM_RULES || []).map(rule => [rule.id, rule.name]));
    const label = platform => names[platform] || platform;
    const syncable = support.filter(item => item.sync_supported).map(item => label(item.platform));
    const manual = support.filter(item => !item.sync_supported).map(item => label(item.platform));
    const hint = $("manageAccountsHint");
    if (hint && syncable.length) {
      hint.textContent = `${syncable.join("、")}可自动同步；其余平台用下面的「保存当前页面」`;
    }
    const why = $("diagnoseWhy");
    if (why && manual.length) {
      why.textContent = `${manual.join("、")}的收藏列表现在还读不了`;
    }
    // **手动保存对多数平台是唯一的路，不该叫「备用」。**
    // 九个平台里能自动同步的只有两个，其余七个只能这样存。
    const summary = $("saveSummary");
    if (summary) {
      summary.textContent = manual.length > syncable.length
        ? `保存当前页面（${manual.length} 个平台只能这样存）`
        : "保存当前页面";
    }
    openSavePanelWhenItIsTheOnlyWay();
  }

  /** 当前这一页所属的平台没法自动同步时，**把保存面板默认展开**（v0.0.0.14）。
   *
   * 它原来叫「备用：保存当前页面」，收在一个折叠面板里。
   * 而九个平台里只有两个能自动同步——**其余七个手动保存是唯一的路**，
   * 把唯一的路收在一个写着「备用」的折叠框里，等于让他自己去翻。
   *
   * 不无条件展开：他正看着 B 站或书签时，自动同步才是主路，
   * 展开只会占掉弹窗的高度。**按他当前看的这一页决定。**
   */
  function openSavePanelWhenItIsTheOnlyWay() {
    const button = $("savePage");
    const panel = button && button.closest("details");
    if (!panel || !platform) return;
    const support = platformSupport[platform.id];
    // 读不到能力表就不动它——宁可保持原样，也不要凭猜改变界面。
    if (!support) return;
    if (support.sync_supported === false) panel.open = true;
  }

  async function refresh() {
    let serviceConnected = true;
    try {
      const [accountData, runData, bootstrapData] = await Promise.all([
        SA.api("/v1/accounts", { timeoutMs: 7000 }),
        SA.api("/v1/sync-runs?limit=100", { timeoutMs: 7000 }),
        SA.api("/v1/extension/bootstrap", { timeoutMs: 7000 })
      ]);
      accounts = accountData.items || [];
      runs = runData.items || [];
      bootstrap = bootstrapData;
      // **服务端已经把「哪些平台能自动同步」下发过来了，此前这里把它扔掉。**
      // 于是弹窗里那几句话全是写死的，改一次扫描范围就漂一次——
      // 诊断面板那句「小红书、抖音、B站、快手的收藏列表现在还读不了」
      // 在 B 站接上之后整整两个版本都还挂在那儿。
      platformSupport = Object.fromEntries(
        (accountData.supported_platforms || []).map(item => [item.platform, item]));
      // /health 不需要鉴权，单独取一次；读不到就当没这回事（保持原样）
      workerState = await SA.api("/health", { timeoutMs: 5000 })
        .then(payload => payload.worker || null).catch(() => null);
      const pending = runs.filter(run => ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting", "failed", "blocked_environment"].includes(run.status)).length;
      $("taskCount").textContent = String(pending);
      $("taskCount").classList.toggle("hidden", pending === 0);
    } catch (_) {
      serviceConnected = false;
      accounts = [];
      runs = [];
      bootstrap = null;
    }
    renderPlatformCopy();
    renderSummary(serviceConnected);
    renderAccounts();
    renderDestinations();
    return serviceConnected;
  }

  async function syncAll() {
    const serviceConnected = await refresh();
    if (!serviceConnected) {
      await chrome.runtime.openOptionsPage();
      return;
    }
    const connected = accounts.filter(account => ["connected", "degraded"].includes(account.connection_state));
    if (!connected.length) {
      await chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" });
      window.close();
      return;
    }
    const active = runs.some(run => ["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"].includes(run.status));
    if (active) {
      await chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" });
      window.close();
      return;
    }
    setBusy(true);
    try {
      const result = await chrome.runtime.sendMessage({ type: "SA_SYNC_ALL_ACCOUNTS" });
      if (!result?.ok) throw new Error(result?.error || "没有可同步的已连接账号");
      showStatus(result.message || `已将 ${Number(result.queuedCount || connected.length)} 个账号加入后台同步队列。`, "success");
      await refresh();
    } catch (error) {
      showStatus(`无法启动同步：${error?.message || "未知错误"}`, "error");
    } finally { setBusy(false); }
  }

  async function runCapture() {
    setBusy(true);
    showStatus("正在保存当前页面；这是账号批量同步之外的备用入口。", "needs");
    try {
      config = await SA.setConfig({ relationType: $("relationType").value, collectionKey: $("collectionKey").value.trim() });
      const response = await chrome.runtime.sendMessage({
        type: "SA_CAPTURE_ACTIVE", mode: "page", source: "popup_fallback_current_page",
        relationType: config.relationType, collectionKey: config.collectionKey, destinationIds: config.destinationIds
      });
      if (!response?.ok) throw new Error(response?.error || "保存失败");
      showStatus(`当前页面已保存。${response.destinationWarningCount ? "部分导出需要处理。" : "后台将继续归档和导出。"}`, response.destinationWarningCount ? "needs" : "success");
      await refresh();
    } catch (error) { showStatus(`保存失败：${error?.message || "未知错误"}`, "error"); }
    finally { setBusy(false); }
  }

  async function initCurrentPage() {
    try {
      tab = await SA.activeTab();
      platform = SA.platformFromUrl(tab.url);
      $("platformBadge").textContent = platform.name;
      $("pageTitle").textContent = tab.title || "当前页面";
      config = await SA.getConfig();
      $("relationType").value = config.relationType;
      $("collectionKey").value = config.collectionKey;
      await renderAuthorization();
    } catch (error) {
      $("pageTitle").textContent = "当前页面不可读取";
      $("savePage").disabled = true;
    }
  }

  /** 诊断：这个平台的收藏页到底请求了哪些接口（v0.0.0.7 / T08 前置）。
   *
   * ## 为什么需要人配合
   *
   * 小红书/抖音/B站/快手 的收藏列表读不了，缺的不是代码，是**平台自己返回的
   * 数据长什么样**——而那只存在于 Owner 已登录的浏览器里。我拿不到，
   * 也不该拿：那需要他的登录态。
   *
   * 这颗按钮把他要做的减到「打开收藏页 → 点一下 → 滚几屏」。
   *
   * ## 只记形态，不读内容
   *
   * 观察器抄回来的响应体留在 background 的内存缓冲里；这里只问
   * SA_GET_NET_CAPTURES，它**只回地址、条数与总字节数，不回响应体**。
   * 页面上显示的、以及让用户复制的，都只有地址。
   *
   * 用的是两块早就建好、却一直没有任何界面能触发的管道
   * （SA_INSTALL_NET_OBSERVER / SA_GET_NET_CAPTURES）——
   * find_messages_with_only_one_end 里那两条例外，就是它们。
   */
  async function runDiagnosis() {
    const button = $("diagnose");
    const output = $("diagnoseResult");
    const copyButton = $("diagnoseCopy");
    button.disabled = true;
    const original = button.textContent;
    try {
      const tab = await SA.activeTab();
      // shared.js 导出的是 platformFromUrl，返回规则对象。
      // （第一版写成 SA.detectPlatform / SAExtensionUtils —— 两个都不存在，
      //   而属性调用是我那道「调用了不存在的函数」的门看不见的盲区。）
      const platform = SA.platformFromUrl(tab.url)?.id || "";
      // **先把话说在前面。** platformFromUrl 认不出来时会回落到 generic-web，
      // 而它的权限模式是空的：继续走下去会以一句看不懂的注入失败告终
      // （请求了零个 origin → executeScript 缺 host 权限 → OBSERVER_INSTALL_FAILED）。
      // 与其让人对着「无法在该页面上启动同步」发愣，不如现在就说清楚。
      if (!platform || !SA.patternsForPlatform(platform).length) {
        // **名单从 SA.PLATFORM_RULES 现算，不在这里抄第二份。**
        // 原来这句话把七个平台名硬写在里面。它今天恰好还是对的，
        // 但那正是「第二份名单」的样子——PLATFORM_RULES 一改它就漂，
        // 而没有任何东西会提醒。同一天里第五处假话就是这么来的
        // （首页那句「能自动同步 X / Instagram」比能力声明晚了一轮）。
        const diagnosable = SA.PLATFORM_RULES
          .filter(rule => rule.patterns.length)
          .map(rule => rule.name)
          .join(" / ");
        throw new Error(`这个页面不是可诊断的平台。请先打开${diagnosable} 的收藏页，并确认已登录。`);
      }
      // **浏览器要弹授权框了，先说一声。**
      //
      // installNetObserverForTab 进门就调 requestPlatformPermission，
      // Chrome 会弹一个原生框问「允许此扩展读取 bilibili.com 上的数据吗」。
      // 没人提前说的话，一个说自己「没有技术基础」的人最可能的反应是点「拒绝」——
      // 然后拿到 PLATFORM_PERMISSION_DENIED，而他并不知道自己刚拒绝的是什么。
      // 这一步在他**只按一次**的那条路上，不能靠他猜。
      button.textContent = "浏览器要问你「允许吗」——点允许";
      const installed = await chrome.runtime.sendMessage({
        // diagnostic=true：让 background 按本页域名推前缀。
        // 不然只有 bilibili 有已知前缀，另外三个平台会被当场拒绝——
        // 而这颗按钮存在的目的正是去发现那些前缀。
        type: "SA_INSTALL_NET_OBSERVER", platform, tabId: tab.id, diagnostic: true,
      });
      if (!installed?.ok) throw new Error(installed?.error || "无法在这个页面上开始观察");
      // **等到真的抓到东西为止，而不是死等 10 秒。**
      //
      // 原来是固定 10 秒倒计时，然后不管抓没抓到都收工。这颗按钮 Owner
      // 大概率只会点一次——他说过「能你做的就别让我做」——所以那一次
      // 必须尽量成。滚得慢一点、页面加载久一点，10 秒就空手而归，
      // 而报告只会说「一条都没抓到」，看不出是没请求还是没等够。
      //
      // 改成：每秒问一次，最多 30 秒；抓到之后连续 3 秒没有新增就提前收工
      // （说明这一屏的翻页请求发完了，没必要再让人干等）。
      let captured = { count: 0, urls: [], totalBytes: 0 };
      let quiet = 0;
      for (let elapsed = 0; elapsed < 30; elapsed += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const snapshot = await chrome.runtime.sendMessage({ type: "SA_GET_NET_CAPTURES" }).catch(() => null);
        const count = Number(snapshot?.count || 0);
        if (snapshot) captured = snapshot;
        if (count > 0 && count === Number(captured.count)) quiet += 1; else quiet = 0;
        if (count > 0) {
          button.textContent = quiet >= 3
            ? "够了，正在读…"
            : `已抓到 ${count} 条，继续用滚轮往下滚…`;
          if (quiet >= 3) break;
        } else {
          // **「滚」要说清是用滚轮滚，别点页面。**
          //
          // 这个弹窗一失去焦点就整个关掉，而它一关，正在跑的诊断就断在半路：
          // 抓到的东西不会被读、结果也不会存到服务器。**而 Owner 只按一次。**
          // 用滚轮滚不会夺走焦点，点一下页面会。这行字原来只写「请往下滚动几屏」——
          // 照着做最自然的动作恰好是先点一下页面。
          button.textContent = elapsed < 10
            ? `用滚轮往下滚几屏（别点页面，一点这个窗就关了）…（${10 - elapsed} 秒）`
            : `还没抓到，再用滚轮滚几屏…（还等 ${30 - elapsed} 秒）`;
        }
      }
      const urls = (captured?.urls || []).filter((value, index, all) => all.indexOf(value) === index);
      // **「拦到了」不等于「读得懂」。** 只报地址与字节数的话，
      // 一条 `{"code":0,"message":"OK","data":null}` 看起来完全成功——
      // 而它的真实含义是「这个浏览器没登录」。所以再往前走一步：
      // 把抓到的响应真的读一遍，把结论也写进报告。
      button.textContent = "正在读一遍抓到的内容…";
      const readback = await chrome.runtime.sendMessage({
        type: "SA_PARSE_NET_CAPTURES", platform,
      }).catch(() => null);
      const report = [
        `平台：${platform || "（没认出来）"}`,
        `页面：${String(tab.url || "").split("?")[0]}`,
        `抓到 ${captured?.count || 0} 条响应，共 ${captured?.totalBytes || 0} 字节`,
        `读得懂：${readback?.message_zh || "（没能读一遍）"}`,
        ...(readback && !readback.ok && readback.failureCode
          ? [`失败码：${readback.failureCode}`] : []),
        "",
        ...(urls.length ? urls.map(u => `  ${u}`) : ["  （一条都没抓到——可能这个页面没有翻页请求，试试滚动或切换收藏夹）"]),
      ].join("\n");
      output.textContent = report;
      output.classList.remove("hidden");
      copyButton.classList.remove("hidden");
      // **把结果直接存到他自己的服务器，省掉「你复制给我」这一步。**
      //
      // Owner 的原话：「能你做的就别让我做 我没有技术基础」。
      // 让他复制粘贴一段技术文本，正是这句话要消掉的东西。
      //
      // 只送地址与计数，**不送响应体**——响应体留在 background 的内存缓冲里，
      // 它可能带着平台返回的个人信息，而固化拦截前缀只需要地址。
      // 复制按钮留着：存不上去（没登录、没网）时它仍是退路。
      SA.api("/v1/extension/diagnostics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform, page_url: String(tab.url || ""), urls,
          capture_count: Number(captured?.count || 0),
          readable_count: Number(readback?.readable || 0),
          // 少收下的、没去读的也报上去。缓冲区封顶 200、解析去重后封顶 30，
          // 两处收敛都必要，但**收敛得不留痕迹就危险**：
          // 「抓到 200 条、读得懂 0 条」到底是平台没发那个请求，
          // 还是那条被挤掉了／没轮到读？下一步完全不同。
          dropped_count: Number(readback?.dropped || 0),
          not_parsed_count: Number(readback?.notParsed || 0),
          // **哪几条读得懂——T09 固化拦截前缀就靠这一样。**
          // 只报一个数字等于说了「有三条能读」却不说是哪三条。
          readable_urls: Array.isArray(readback?.readableUrls) ? readback.readableUrls : [],
          note: String(readback?.message_zh || ""),
        }),
        timeoutMs: 15000,
      }).then(() => showStatus("诊断结果已存到你的服务器，不用再复制给谁。", "ok"))
        .catch(() => showStatus("结果存不到服务器，请点下面的「复制」发给开发者。", "needs"));
      copyButton.onclick = async () => {
        try { await navigator.clipboard.writeText(report); showStatus("已复制", "ok"); }
        catch (_) { showStatus("复制失败，请手动选中上面的文字", "error"); }
      };
    } catch (error) {
      showStatus(error?.message || "诊断失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  $("diagnose").addEventListener("click", runDiagnosis);
  $("primarySync").addEventListener("click", syncAll);
  $("manageAccounts").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_ACCOUNT_CENTER" }).then(() => window.close()));
  $("refresh").addEventListener("click", refresh);
  $("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("manageDestinations").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("savePage").addEventListener("click", runCapture);
  $("taskCenter").addEventListener("click", () => chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" }).then(() => window.close()));
  $("openLibrary").addEventListener("click", async () => chrome.tabs.create({ url: (await SA.getConfig()).libraryUrl }));

  Promise.all([refresh(), initCurrentPage()]).catch(error => showStatus(error?.message || "插件初始化失败", "error"));
})();
