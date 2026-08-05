/* global SA */
importScripts("shared.js", "content/platform-catalog.js", "content/extension-utils.js", "cookie-export.js");

const MENU_SAVE = "social-archive-save-page";
const MENU_SELECTION = "social-archive-save-selection";
const PWA_BRIDGE_URL_PATTERNS = [
  "https://social-archive.linzezhang.com/*",
  "http://127.0.0.1:8765/*",
  "http://localhost:8765/*"
];

async function ensureMenus() {
  await chrome.contextMenus.removeAll();
  chrome.contextMenus.create({ id: MENU_SAVE, title: "保存到我的档案馆", contexts: ["page", "link", "image", "video"] });
  chrome.contextMenus.create({ id: MENU_SELECTION, title: "保存选中文本到我的档案馆", contexts: ["selection"] });
}

async function injectExtractor(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/extract-core.js", "content/extract.js"] });
}

async function reconnectOpenPwaBridgeTabs() {
  const tabs = await chrome.tabs.query({ url: PWA_BRIDGE_URL_PATTERNS }).catch(() => []);
  const completeTabs = tabs.filter(tab => typeof tab?.id === "number" && tab.status === "complete");
  await Promise.all(completeTabs.map(tab =>
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["bridge.js"] }).catch(() => null)
  ));
  return { found: tabs.length, injected: completeTabs.length };
}

async function extractFromTab(tab, mode) {
  await injectExtractor(tab.id);
  const response = await chrome.tabs.sendMessage(tab.id, { type: "SA_EXTRACT", mode });
  if (!response?.ok) throw new Error(response?.error || "页面结构已变化，暂时无法读取");
  return response;
}

function serverDestinations(config) {
  const ids = config.destinationIds || ["social_archive"];
  return config.obsidianLocalEnabled ? ids.filter(id => id !== "obsidian") : ids;
}

function buildCaptureBody(record, tabUrl, config, overrides = {}) {
  const platform = SA.platformFromUrl(record.url || tabUrl);
  return {
    platform: platform.id,
    url: record.url || tabUrl,
    relation_type: overrides.relationType || config.relationType || "saved",
    collection_key: overrides.collectionKey ?? config.collectionKey ?? "",
    title: record.title || null,
    author_name: record.author_name || null,
    text: record.text || null,
    published_at: record.published_at || null,
    media_urls: (record.media_urls || []).filter(url => /^https?:/i.test(url)).slice(0, 100),
    raw_metadata: { ...(record.raw_metadata || {}), capture_source: overrides.source || "toolbar" },
    requested_levels: ["L0", "L1", "L3"],
    destination_ids: overrides.destinationIds || serverDestinations(config)
  };
}

function safeFileSegment(value, fallback) {
  const text = String(value || fallback || "未命名").normalize("NFKC").replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ").replace(/\s+/g, " ").trim();
  return (text || fallback || "未命名").slice(0, 120);
}

async function exportLocalObsidian(response, record, config) {
  if (!config.obsidianLocalEnabled || !config.destinationIds.includes("obsidian")) return { status: "not_selected" };
  if (!config.obsidianLocalToken) return { status: "needs_user_action", error: "Obsidian 令牌缺失" };
  const markdown = await SA.apiText(`/v1/library/${encodeURIComponent(response.content_id)}/markdown`, { timeoutMs: 15000 });
  const platform = SA.platformFromUrl(record.url || "").id;
  const path = `Social Archive/${safeFileSegment(platform, "web")}/${safeFileSegment(record.title, response.content_id)}-${response.content_id.slice(-8)}.md`;
  const result = await fetch(`${config.obsidianLocalUrl.replace(/\/$/, "")}/vault`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${config.obsidianLocalToken}`,
      "Content-Type": "text/markdown; charset=utf-8",
      "X-Social-Archive-Path": encodeURIComponent(path)
    },
    body: markdown
  });
  if (!result.ok) throw new Error(`Obsidian HTTP ${result.status}`);
  return { status: "done", path };
}

async function captureRecord(record, tabUrl, config, overrides = {}) {
  const body = buildCaptureBody(record, tabUrl, config, overrides);
  const response = await SA.api("/v1/captures", { method: "POST", body: JSON.stringify(body), timeoutMs: 30000 });
  try {
    response.local_obsidian = await exportLocalObsidian(response, record, config);
  } catch (error) {
    response.local_obsidian = { status: "needs_user_action", error: error?.message || "Obsidian 写入失败" };
  }
  return response;
}

async function captureActive(message = {}, sourceTab = null) {
  const tab = sourceTab?.id && sourceTab?.url ? sourceTab : await SA.activeTab();
  const config = await SA.getConfig();
  const extracted = await extractFromTab(tab, message.mode === "list" ? "list" : "page");
  const items = message.mode === "list" ? extracted.items : [extracted.page];
  if (message.mode === "list") {
    for (const item of items) {
      item.raw_metadata = {
        ...(item.raw_metadata || {}),
        scan_completeness: extracted.completeness || "partial",
        scan_context: extracted.scan_context || { mode: "visible_only", no_autoscroll: true }
      };
    }
  }
  if (!items.length) return { ok: false, state: "needs_user_action", error: "当前可见区域没有可读取的内容" };
  let saved = [];
  const failed = [];
  const localDestinationErrors = [];
  if (message.mode === "list") {
    try {
      const batch = await SA.api("/v1/captures/batch", {
        method: "POST",
        body: JSON.stringify({ items: items.map(item => buildCaptureBody(item, tab.url, config, message)) }),
        timeoutMs: 60000
      });
      saved = batch.items || [];
      for (const error of batch.errors || []) failed.push(error.detail || "保存失败");
      if (config.obsidianLocalEnabled && config.destinationIds.includes("obsidian")) {
        for (let index = 0; index < saved.length; index += 1) {
          try { saved[index].local_obsidian = await exportLocalObsidian(saved[index], items[index] || {}, config); }
          catch (error) { localDestinationErrors.push(error?.message || "Obsidian 写入失败"); }
        }
      }
    } catch (error) {
      failed.push(error?.message || "批量保存失败");
    }
  } else {
    try { saved.push(await captureRecord(items[0], tab.url, config, message)); }
    catch (error) { failed.push(error?.message || "保存失败"); }
  }
  if (!saved.length) return { ok: false, state: "needs_user_action", error: failed[0] || "保存失败" };
  await chrome.action.setBadgeBackgroundColor({ color: localDestinationErrors.length ? "#9a6700" : "#1f7a4c" });
  await chrome.action.setBadgeText({ text: String(saved.length) });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2500);
  return {
    ok: true,
    savedCount: saved.length,
    failedCount: failed.length,
    destinationWarningCount: localDestinationErrors.length,
    destinationWarnings: localDestinationErrors,
    jobIds: saved.flatMap(item => item.job_ids || []),
    detailUrls: saved.map(item => item.detail_url)
  };
}

async function injectFabIfAuthorized(tabId, url) {
  if (!/^https?:/i.test(url || "")) return;
  const config = await SA.getConfig();
  if (!config.showFloatingButton) return;
  const platform = SA.platformFromUrl(url);
  if (platform.id === "generic-web") return;
  const state = await SA.permissionState(platform.id);
  if (!state.authorized) return;
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/fab.js"] }).catch(() => {});
}


const PENDING_CONNECTIONS_KEY = "saPendingAccountConnections";
const SYNC_QUEUE_KEY = "saAccountSyncQueue";
const SYNC_QUEUE_LOCK_KEY = "saAccountSyncQueueLock";
const SYNC_QUEUE_LAST_RESULT_KEY = "saAccountSyncQueueLastResult";
const SYNC_CONTROL_KEY = "saSyncRunControls";
const SYNC_QUEUE_ALARM = "sa-account-sync-queue";
// T08：MAIN world 观察器抄回来的原始响应，先缓冲在 service worker 里。
// 上限存在的理由：一次大翻页可能抄回几十兆，撑爆 worker 会把整条同步弄挂。
const NET_CAPTURE_LIMIT = 200;
const RELAY_SCRIPT_ID = "sa-net-relay";
const OBSERVER_SCRIPT_ID = "sa-net-observer";
// 缓冲区满了之后丢掉的条数。**必须报出去**——静默丢弃看起来就是「一条都没抓到」。
let netCapturesDropped = 0;

/** 等这个标签页重新加载完。
 *
 * 原来是硬等 1500ms。硬等的问题不是不准，是**它把「等够了」和「等到了」
 * 混成一件事**：网慢一点就等不到，网快一点就白等。
 */
/** 把观察器装到某个标签页上——**诊断按钮背后真正跑的那段**。
 *
 * 从消息处理器里整段挪出来，只为一件事：**让演练能调到它本人**。
 * 演练照抄一遍处理器的顺序也能跑，但那测的是抄件；抄件和正本一分叉，
 * 演练就会在正本坏掉的时候继续绿——而这一天里正本恰好改了两处。
 */
async function installNetObserverForTab({ platform, tabId, diagnostic }) {
  // **每次诊断都是一次新的测量，先把上一次的清干净。**
  //
  // 缓冲区原来从头到尾没人清过，只靠 service worker 睡着（约 30 秒）自然消失。
  // 于是连按两次诊断，第二次会把第一次的响应一起数进去——「拦到 N 条」对不上这一次；
  // 换个平台再按更糟：拿 xiaohongshu 去解析上一轮 bilibili 的字节，全判读不懂，
  // 报回来的第一条问题完全指错方向。
  //
  // 这个缺口是**演练替产品做了它该做的事**才露出来的：探针里得手写
  // netCaptureBuffer.length = 0 才量得准——要手动清，说明产品自己没清。
  netCaptureBuffer.length = 0;
  netCapturesDropped = 0;
  observerStateByTab.delete(tabId);
    // **诊断模式：前缀由这个标签页自己的域名推出，不查表。**
    //
    // 死循环否则会成立：诊断按钮存在的目的就是**去发现**这些前缀，
    // 而下面那张表只有 bilibili 有值（xiaohongshu / douyin / kuaishou 都是 null），
    // 于是按钮在 3/4 的平台上当场被拒——工具拒绝执行它自己被造出来要做的事。
    //
    // 安全上不放宽：前缀**只从 tab.url 的域名推**，调用方给什么都不采信。
    // 也就是说它最多只能看见「这个页面自己发出的、发往它自己域名的请求」。
    let prefixes = globalThis.SAPlatformCatalog?.interceptPrefixes?.(platform);
    // 两条路都要用到这个标签页的地址：诊断用它推前缀，注册内容脚本用它推 matches。
    const observedTab = await chrome.tabs.get(tabId).catch(() => null);
    if (diagnostic) {
      let host = "";
      try { host = new URL(observedTab?.url || "").hostname; } catch (_) { host = ""; }
      // space.bilibili.com → bilibili.com；只留可注册域，覆盖它的 API 子域。
      // **IP 地址要整个用**：127.0.0.1 按 slice(-2) 会变成 "0.1"，
      // 那是个既抓不到东西又莫名其妙的前缀。
      const isIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.includes(":");
      const registrable = isIp ? host : host.split(".").slice(-2).join(".");
      if (!registrable) {
        return { ok: false, state: "failed", failureCode: "DIAGNOSTIC_NO_HOST",
                 error: "读不出当前页面的域名，无法开始诊断。" };
      }
      prefixes = [registrable];
    }
    // prefixes 为 null = 还没有实测过的前缀。**必须在这里显式失败**：
    // 装一个前缀为空的观察器等于永远拦不到，而且页面一切正常、界面显示已连接——
    // 正是 INV-NO-SILENT-ZERO 要防的那种零。
    if (!Array.isArray(prefixes) || prefixes.length === 0) {
      return {
        ok: false, state: "needs_user_action", platform,
        failureCode: "INTERCEPT_PREFIX_UNKNOWN",
        error: `还没有确认 ${globalThis.SAPlatformCatalog?.platformLabel?.(platform) || platform} 的收藏接口地址，这个平台暂时不能同步。`,
      };
    }
    if (!Number.isInteger(tabId)) return { ok: false, error: "没有可用的平台页面。" };
    // **先要权限，再注入。** executeScript 没有该站点的 host 权限会直接抛，
    // 而那个异常和"注入本身失败"长得一样——用户看到的是「无法在该页面上启动同步」，
    // 却不知道其实只需要点一下授权。这与 T06 把 NOT_LOGGED_IN 和
    // PERMISSION_DENIED 分开是同一条道理：两者的下一步不同，就不能合并成一个错。
    const granted = await SA.requestPlatformPermission(platform).catch(() => false);
    if (!granted) {
      return {
        ok: false, state: "unauthorized", platform,
        failureCode: "PLATFORM_PERMISSION_DENIED",
        error: `没有获得读取${globalThis.SAPlatformCatalog?.platformLabel?.(platform) || platform}页面的授权，无法同步这个平台。`,
      };
    }
    try {
      // **诊断前先刷新这个页面，而且观察器必须比页面自己的 JS 先就位。**
      //
      // 两件事叠在一起，缺一件都抓不到：
      //
      // 其一，观察器对同一次页面加载是幂等的（`if (window[CHANNEL]) return`），
      // 于是**扩展更新之后、页面没重载过**的话，注入进去的新代码会直接返回，
      // 实际生效的还是旧观察器。实测（2026-08-04，真实 Chrome）：
      // 不 reload 时抓到 0 条且自报 installed/ready 全为 true。
      //
      // 其二，原来是「刷新 → 等 1500ms → executeScript」。**那样太晚了。**
      // 实测（2026-08-05，真 Chrome + 回环假站，页面像真收藏夹页那样
      // 只在加载时发一次请求）：自报 installed/ready 仍然全为 true，
      // 抓到 **0 条**——收藏列表那个请求在观察器落地之前就打完了。
      // 上一版演练之所以是绿的，是因为那个假页面每 700ms 重发一次，比现实宽容。
      //
      // 改法：注册成 document_start 的内容脚本再刷新，两个世界的脚本都比页面早。
      // 前缀仍然是随后下发的，那段缝由观察器自己的暂存区补上。
      const origin = (() => {
        try { return new URL(observedTab?.url || "").origin + "/*"; }
        catch (_) { return null; }
      })();
      if (!origin || origin.startsWith("null")) {
        return { ok: false, state: "failed", failureCode: "DIAGNOSTIC_NO_HOST",
                 error: "读不出当前页面的地址，无法开始诊断。" };
      }
      // **先注册中继，再注册观察器。** 顺序反了会漏掉观察器安装瞬间发出的那条
      // SA_OBSERVER_INSTALLED —— 观察器在 IIFE 末尾就 post 了它，
      // 那时如果中继还没挂上监听，这条消息就掉进虚空。
      //
      // 这个顺序是在真实浏览器里跑出来才发现的：Node 沙箱里我是先挂监听
      // 再跑观察器，所以永远看不到这个问题；真实注入顺序是反的。
      // 丢掉 INSTALLED 的后果不是少一条日志——background 会分不清
      // 「观察器装好了」和「注入静默失败了」，正是本项目反复栽跟头的那种盲区。
      await chrome.scripting
        .unregisterContentScripts({ ids: [RELAY_SCRIPT_ID, OBSERVER_SCRIPT_ID] })
        .catch(() => {});
      await chrome.scripting.registerContentScripts([
        { id: RELAY_SCRIPT_ID, matches: [origin], js: ["content/net-relay.js"],
          runAt: "document_start", world: "ISOLATED", persistAcrossSessions: false },
        { id: OBSERVER_SCRIPT_ID, matches: [origin], js: ["net-observer.js"],
          runAt: "document_start", world: "MAIN", persistAcrossSessions: false },
      ]);
      if (diagnostic) {
        await chrome.tabs.reload(tabId);
        await waitForTabComplete(tabId);
      } else {
        // 非诊断路径不刷新用户的页面（那会打断他正在看的东西），
        // 所以当前这一页仍然靠即时注入；注册是给随后的翻页导航用的。
        await chrome.scripting.executeScript({
          target: { tabId }, files: ["content/net-relay.js"],
        });
        await chrome.scripting.executeScript({
          target: { tabId }, world: "MAIN", files: ["net-observer.js"],
        });
      }
      await sendConfigureWithRetry(tabId, prefixes);
      // 配置到达之前发生的请求由观察器扣在暂存区，收到前缀那一刻补发。
      // 这里等一下，让补发的那些走完 中继 → background 这一段。
      await new Promise(resolve => setTimeout(resolve, 900));
      // **注册只为这一次。** 页面里已经跑起来的那份不受影响（翻页照样抓得到），
      // 但不给平台留下一个常驻的 MAIN world 钩子。
      await chrome.scripting
        .unregisterContentScripts({ ids: [RELAY_SCRIPT_ID, OBSERVER_SCRIPT_ID] })
        .catch(() => {});
      // 把观察器**自己报回来的**状态一并交出去。注意它是异步到达的：
      // 这一刻拿不到不等于注入失败，所以只做如实汇报，不拿它当判据。
      const selfReport = observerStateByTab.get(tabId) || null;
      return { ok: true, state: "observing", platform, prefixCount: prefixes.length,
               observerSelfReport: selfReport };
    } catch (error) {
      return { ok: false, state: "failed", failureCode: "OBSERVER_INSTALL_FAILED",
               error: error?.message || "无法在该页面上启动同步。" };
    }
}

async function waitForTabComplete(tabId, timeoutMs = 15000) {
  // reload 是异步的，刚发出去时 status 还是上一次加载留下的 complete，
  // 直接轮询会当场"等到"。先给它一点时间进入 loading。
  await new Promise(resolve => setTimeout(resolve, 300));
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) return false;
    if (tab.status === "complete") return true;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  return false;
}

/** 把前缀下发给中继，失败就再试几次。
 *
 * 中继是 document_start 注册的，正常情况下早就在听了；但页面刚开始加载的
 * 那一瞬间 sendMessage 会以「接收端不存在」被拒。这里退让重试，
 * **而不是把这一次失败当成没装上**——那正是本项目反复认错的那种盲区。
 */
async function sendConfigureWithRetry(tabId, prefixes, attempts = 5) {
  let lastError = null;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await chrome.tabs.sendMessage(tabId, {
        type: "SA_OBSERVER_CONFIGURE", urlPrefixes: prefixes,
      });
    } catch (error) {
      lastError = error;
      await new Promise(resolve => setTimeout(resolve, 250 * (i + 1)));
    }
  }
  throw lastError || new Error("无法把拦截配置发给页面。");
}
const netCaptureBuffer = [];
// 观察器自报的安装/就绪状态（v0.0.0.7 / T08）。中继一直在发 SA_NET_OBSERVER_STATE，
// **而 background 此前没有这条消息的处理体**——那条自报掉进虚空。
// 它掉了的后果正是安装那段注释里写明不许发生的：分不清「观察器装好了」
// 和「注入静默失败了」。按 tab 记，标签页关掉就没意义了。
const observerStateByTab = new Map();
const MIRROR_TAB_PREFIX = "saMirrorTab:";
const ACTIVE_SYNC_STATES = new Set(["queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"]);

// ── MV3 service worker 会在同步跑到一半时被杀掉 ──────────────────────
//
// 这不是异常情况，是 MV3 的**常态**：worker 空闲约 30 秒就被回收，
// 长任务跑到一半被终止，`finally` 不会执行。
//
// 这个常量是本次 worker 实例的身份。模块作用域在**每次 service worker
// 启动时重新求值**，所以它天生就标识「当前这个 worker」。
// 关键推论：MV3 同一时刻只有一个 worker 实例，所以
// **storage 里一把 workerId 不等于当前值的锁，一定是死锁**
// ——持有它的那个 worker 已经不在了，不必等它超时。
const WORKER_INSTANCE_ID = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// 被 worker 之死打断的任务重试几次。到顶之后必须**显式失败**而不是安静消失
// （INV-NO-SILENT-ZERO）——否则用户看到的又是一次没有解释的 0 条。
const MAX_SYNC_ATTEMPTS = 3;

async function getPendingConnections() {
  const stored = await chrome.storage.local.get({ [PENDING_CONNECTIONS_KEY]: {} });
  return stored[PENDING_CONNECTIONS_KEY] || {};
}

async function setPendingConnection(platform, value) {
  const pending = await getPendingConnections();
  if (value) pending[platform] = value;
  else delete pending[platform];
  await chrome.storage.local.set({ [PENDING_CONNECTIONS_KEY]: pending });
}


async function getSyncQueue() {
  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_KEY]: [] });
  return Array.isArray(stored[SYNC_QUEUE_KEY]) ? stored[SYNC_QUEUE_KEY] : [];
}

async function setSyncQueue(items) {
  await chrome.storage.local.set({ [SYNC_QUEUE_KEY]: items });
}

async function getSyncControls() {
  const stored = await chrome.storage.local.get({ [SYNC_CONTROL_KEY]: {} });
  return stored[SYNC_CONTROL_KEY] || {};
}

async function setSyncControl(syncRunId, action = null) {
  if (!syncRunId) return;
  const controls = await getSyncControls();
  if (action) controls[syncRunId] = { action, updatedAt: Date.now() };
  else delete controls[syncRunId];
  await chrome.storage.local.set({ [SYNC_CONTROL_KEY]: controls });
}

async function getSyncControl(syncRunId) {
  if (!syncRunId) return null;
  const controls = await getSyncControls();
  return controls[syncRunId] || null;
}

async function removeQueuedSync({ syncRunId = null, accountId = null } = {}) {
  const queue = await getSyncQueue();
  const kept = queue.filter(item => {
    if (syncRunId && item.syncRunId === syncRunId) return false;
    if (accountId && item.accountId === accountId) return false;
    return true;
  });
  if (kept.length !== queue.length) await setSyncQueue(kept);
  return queue.length - kept.length;
}

// v0.0.0.7 / T03：原先这里向所有标签页广播 SA_MIRROR_CONTROL，
// 让 DOM 抓取的 content script 中途停下。抓取器已删，广播没有接收方——
// 留着它会让"暂停已下发"看着成立而实际什么都没发生。
// 暂停/取消并没有因此失效：stopStateFor 从本地 storage 与服务端 sync-run
// 两处读控制态，编排层每一轮都查，这才是真正生效的那条路。
// T08 引入 MAIN-world 拦截时会带来它自己的控制通道，届时再建。

async function stopStateFor(syncRunId) {
  const local = await getSyncControl(syncRunId);
  if (local?.action === "pause" || local?.action === "cancel") return local.action;
  if (!syncRunId) return null;
  const run = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 8000 }).catch(() => null);
  if (run?.status === "paused") return "pause";
  if (run?.status === "cancelled") return "cancel";
  return null;
}

async function controlSyncRun({ syncRunId, accountId = null, action }) {
  const allowed = new Set(["pause", "resume", "cancel", "retry"]);
  if (!syncRunId || !allowed.has(action)) throw new Error("同步控制参数无效");
  const before = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 10000 });
  const effectiveAccountId = accountId || before.source_account_id;
  const result = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}/control`, {
    method: "POST",
    body: JSON.stringify({ action }),
    timeoutMs: 15000
  });

  if (action === "pause" || action === "cancel") {
    await setSyncControl(syncRunId, action);
    await removeQueuedSync({ syncRunId, accountId: effectiveAccountId });
  } else {
    await setSyncControl(syncRunId, null);
    await enqueueAccountSync({
      accountId: effectiveAccountId,
      syncRunId,
      triggerType: action === "retry" ? "retry" : "resume"
    });
  }

  const messages = {
    pause: "同步已暂停，已完成内容不会丢失",
    resume: "同步已恢复并重新加入后台队列",
    cancel: "同步已取消，已完成内容仍保留在资料库",
    retry: "同步已重新加入后台队列"
  };
  return { ok: true, ...result, accountId: effectiveAccountId, message: messages[action] };
}

async function scheduleSyncQueue(delayInMinutes = 0.5) {
  // **周期闹钟，不是一次性的。** 原来用的是只有 delayInMinutes 的一次性闹钟，
  // 靠 processSyncQueue 的 finally 去排下一次。worker 被杀时 finally 不执行，
  // 于是没有任何东西会再唤醒它——队列就永远停在那儿。
  // 周期闹钟由浏览器持有，worker 死了它照样会把 worker 拉起来，
  // 这是 MV3 里唯一可靠的恢复入口。空闲时由 clearSyncQueueAlarmIfIdle 撤掉。
  await chrome.alarms.create(SYNC_QUEUE_ALARM, {
    delayInMinutes: Math.max(0.5, Number(delayInMinutes || 0.5)),
    periodInMinutes: 1,
  });
}

async function clearSyncQueueAlarmIfIdle() {
  // 队列空了、也没有在跑的任务，就撤掉周期闹钟，别白白唤醒 worker。
  const [queue, stored] = await Promise.all([
    getSyncQueue(),
    chrome.storage.local.get({ [SYNC_QUEUE_LOCK_KEY]: null }),
  ]);
  if (!queue.length && !stored[SYNC_QUEUE_LOCK_KEY]) {
    await chrome.alarms.clear(SYNC_QUEUE_ALARM);
  }
}

async function reportSyncGaveUp(item) {
  // 把「这次同步我不再试了」报给服务端，让那次 run 从 queued 走到终态。
  //
  // 不报的后果：扩展这边收拾干净了，服务端那次 run 永远停在 queued，
  // 界面就永远转圈——用户看到的和什么都没修一模一样。
  //
  // 用的是既有的「关系终批」机制（scope_type=relation + 空 items +
  // completeness=failed），不新开协议：服务端 _finalize_relation_scope
  // 收到 failed 就会把这次 run 落到 failed。
  if (!item?.syncRunId) return { reported: false, reason: "没有 syncRunId，服务端本来就没有这次 run" };
  try {
    // 关系类型问**这次 run 自己**，不要从平台去猜。
    // run.relation_scope 就是当初发起时写进去的那一组，是权威。
    // 从平台猜会漏掉 Chrome 书签：它的平台是 generic-web，平台目录里
    // 根本没有这一条（它走 syncChromeBookmarks 那条独立路径，
    // 关系类型写死是 "bookmark"）——而那恰恰是最常用的账号。
    const run = await SA.api(`/v1/sync-runs/${encodeURIComponent(item.syncRunId)}`, { timeoutMs: 8000 })
      .catch(() => null);
    let relation = (run?.relation_scope || [])[0];
    if (!relation) {
      const account = (await listAccounts()).find(entry => entry.id === item.accountId);
      relation = platformSpec(account?.platform)?.relations?.[0];
    }
    if (!relation) return { reported: false, reason: "认不出这次同步的关系类型" };
    await sendSyncBatch(item.syncRunId, {
      relation_type: relation,
      scope_type: "relation",
      items: [],
      completeness: "failed",
      batch_index: 0,
      has_more: false,
      failure_code: "SYNC_INTERRUPTED",
      cursor: { interrupted_attempts: Number(item.attempts || 0) },
    });
    return { reported: true };
  } catch (error) {
    // 报不上去（离线、run 已终态、令牌过期）不能反过来把恢复流程弄挂。
    // 队列这边照样收拾干净，服务端那次 run 由它自己的超时兜底。
    return { reported: false, reason: error?.message || "上报失败" };
  }
}

async function reclaimAbandonedSyncWork() {
  // 把上一个 worker 死掉时留下的残局收回来。
  //
  // 判据不是「锁过期了没」而是「**持锁的 worker 还在不在**」：
  // MV3 同一时刻只有一个 worker 实例，所以 workerId 对不上就说明它已经没了，
  // 不必等那两个小时的超时——那两个小时里用户点什么都是「busy」。
  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_LOCK_KEY]: null });
  const lock = stored[SYNC_QUEUE_LOCK_KEY];
  if (lock && lock.workerId && lock.workerId !== WORKER_INSTANCE_ID) {
    await chrome.storage.local.remove(SYNC_QUEUE_LOCK_KEY);
  }

  const queue = await getSyncQueue();
  let changed = false;
  const kept = [];
  for (const item of queue) {
    // 标了 startedAt 却不是本 worker 起的 —— 它是被中断的，不是在跑的。
    if (!item.startedAt || item.workerId === WORKER_INSTANCE_ID) { kept.push(item); continue; }
    changed = true;
    if (Number(item.attempts || 0) >= MAX_SYNC_ATTEMPTS) {
      // 到顶了：**显式失败，不能安静地从队列里消失**。
      // 安静消失的后果就是用户看到一次没有解释的 0 条，正是这一版要消灭的东西。
      await chrome.storage.local.set({
        [SYNC_QUEUE_LAST_RESULT_KEY]: {
          ok: false, accountId: item.accountId, syncRunId: item.syncRunId || null,
          failureCode: "SYNC_INTERRUPTED", attempts: Number(item.attempts || 0),
          error: "同步被浏览器中断了多次，没有跑完。",
          finishedAt: Date.now(),
        },
      });
      // 光在本地记一笔不够：**服务端那次 run 还停在 queued**，界面一直转圈。
      // 上面这条 lastResult 现在没有任何界面在读，真正被用户看见的是服务端的
      // sync_run 状态。所以必须把"我放弃了"告诉服务端。
      await reportSyncGaveUp(item);
      continue;
    }
    // 还能再试：清掉在跑标记，放回队列
    kept.push({ ...item, startedAt: null, workerId: null, updatedAt: Date.now() });
  }
  if (changed) await setSyncQueue(kept);
  return { reclaimed: changed, queued: kept.length };
}

async function enqueueAccountSync({ accountId, syncRunId = null, tabId = null, profileUrl = "", triggerType = "manual" }) {
  if (!accountId) throw new Error("账号不存在");
  const active = (await listSyncRuns()).find(run => run.source_account_id === accountId && ACTIVE_SYNC_STATES.has(run.status));
  if (active && (!syncRunId || active.id !== syncRunId)) {
    return { ok: true, state: "already_running", accountId, syncRunId: active.id, message: "该账号已经在同步" };
  }
  const queue = await getSyncQueue();
  const existing = queue.find(item => item.accountId === accountId);
  if (existing) {
    existing.syncRunId = existing.syncRunId || syncRunId;
    existing.tabId = existing.tabId || tabId;
    existing.profileUrl = existing.profileUrl || profileUrl;
    existing.triggerType = triggerType || existing.triggerType;
    existing.updatedAt = Date.now();
  } else {
    queue.push({ accountId, syncRunId, tabId, profileUrl, triggerType, enqueuedAt: Date.now(), updatedAt: Date.now() });
  }
  await setSyncQueue(queue);
  await scheduleSyncQueue();
  return { ok: true, state: "queued", accountId, syncRunId, queuedCount: queue.length, message: "同步已加入后台队列" };
}

async function enqueueAllAccounts(triggerType = "manual") {
  const connected = (await listAccounts()).filter(item => ["connected", "degraded"].includes(item.connection_state));
  // 同步不了的平台**根本不进队列**——进了就会每分钟抢一次用户的标签页。
  const capability = await Promise.all(connected.map(item => platformCanSyncNow(item.platform)));
  const accounts = connected.filter((_, index) => capability[index]);
  const results = [];
  for (const account of accounts) {
    try { results.push(await enqueueAccountSync({ accountId: account.id, triggerType })); }
    catch (error) { results.push({ ok: false, accountId: account.id, error: error?.message || "加入同步队列失败" }); }
  }
  return { ok: results.some(item => item.ok), state: "queued", queuedCount: results.filter(item => item.ok).length, results };
}

async function processSyncQueue() {
  // 每次进来先收残局：上一个 worker 可能是在跑到一半时被杀掉的。
  await reclaimAbandonedSyncWork();

  const stored = await chrome.storage.local.get({ [SYNC_QUEUE_LOCK_KEY]: null });
  const lock = stored[SYNC_QUEUE_LOCK_KEY];
  if (lock && lock.workerId === WORKER_INSTANCE_ID) {
    // 只有**本 worker 自己**持的锁才算真的在跑（防同一实例内并发进入）。
    // 别的 worker 留下的锁已经在 reclaim 里清掉了。
    return { ok: true, state: "busy" };
  }

  const queue = await getSyncQueue();
  const index = queue.findIndex(entry => !entry.startedAt);
  if (index < 0) {
    await clearSyncQueueAlarmIfIdle();
    return { ok: true, state: "empty" };
  }
  const item = queue[index];

  const queuedControl = await getSyncControl(item.syncRunId);
  if (queuedControl?.action === "pause" || queuedControl?.action === "cancel") {
    queue.splice(index, 1);
    await setSyncQueue(queue);
    return { ok: true, state: queuedControl.action === "pause" ? "paused" : "cancelled", syncRunId: item.syncRunId };
  }

  // **不 shift。** 原来是先把条目从队列里取出来再干活，worker 中途被杀
  // 这条任务就彻底消失了：队列里没有、服务端那次 run 永远停在 queued、
  // 界面一直转圈。现在改成原地标记「在跑」，跑完才移除——
  // 被打断的话 reclaimAbandonedSyncWork 会把标记清掉让它重来。
  queue[index] = {
    ...item,
    startedAt: Date.now(),
    workerId: WORKER_INSTANCE_ID,
    attempts: Number(item.attempts || 0) + 1,
    updatedAt: Date.now(),
  };
  await setSyncQueue(queue);
  await chrome.storage.local.set({
    [SYNC_QUEUE_LOCK_KEY]: { accountId: item.accountId, startedAt: Date.now(), workerId: WORKER_INSTANCE_ID },
  });

  let result;
  try {
    result = await syncAccountById(item.accountId, item);
    await chrome.storage.local.set({ [SYNC_QUEUE_LAST_RESULT_KEY]: { ...result, accountId: item.accountId, finishedAt: Date.now() } });
  } catch (error) {
    result = { ok: false, accountId: item.accountId, error: error?.message || "同步失败", finishedAt: Date.now() };
    await chrome.storage.local.set({ [SYNC_QUEUE_LAST_RESULT_KEY]: result });
  } finally {
    // 跑完了（不管成没成）才把它从队列里摘掉。
    await removeQueuedSync({ accountId: item.accountId, syncRunId: item.syncRunId });
    await chrome.storage.local.remove(SYNC_QUEUE_LOCK_KEY);
    if ((await getSyncQueue()).length) await scheduleSyncQueue();
    else await clearSyncQueueAlarmIfIdle();
  }
  return result;
}

async function listAccounts() {
  const response = await SA.api("/v1/accounts", { timeoutMs: 10000 });
  return response.items || [];
}

/** 这个平台现在真的同步得动吗（v0.0.0.7 / INV-ZERO-BARRIER）。
 *
 * ## 为什么必须在这一层拦，而不只是藏起按钮
 *
 * 界面上把「立即同步」藏掉之后，**队列照跑**：每分钟一次的
 * processSyncQueue 取出任务 → runBrowserAccountSync →
 * navigateMirrorTab 用 `chrome.tabs.update(tabId, { url, active: true })`
 * **把用户的标签页导航到收藏页并切到前台** → acquireRelationItems 抛错 →
 * 下一分钟再来一次。
 *
 * Owner 的原话：「软件抽风 每次都是把目标网页开了关关了开」。
 * 那就是这个循环。**藏按钮只挡住了入口之一，真正干活的那条路没拦。**
 *
 * 能力由服务端说了算（account_sync.SYNCABLE_NOW），扩展照着做，
 * 不在这里维护第二份名单。
 */
/** 把这次同步交给服务端，一个标签页都不碰。 */
async function startServerSideSync(accountId, triggerType = "manual") {
  const started = await SA.api(`/v1/accounts/${encodeURIComponent(accountId)}/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trigger_type: triggerType }),
    timeoutMs: 20000,
  });
  return { ok: true, state: "queued", handledBy: "server",
           syncRunId: started?.sync_run_id || null,
           message_zh: started?.next_action_zh || "同步已开始。" };
}

async function platformCapability(platform) {
  try {
    const response = await SA.api("/v1/accounts", { timeoutMs: 10000 });
    const entry = (response.supported_platforms || []).find(item => item.platform === platform);
    // 问不到就按「能同步、且要浏览器参与」处理：宁可跑一次失败的同步，
    // 也不要因为一次网络抖动把本来能用的平台全体停掉。
    return {
      canSync: entry ? entry.sync_supported !== false : true,
      serverHandled: entry ? entry.server_handled === true : false,
    };
  } catch (_) {
    return { canSync: true, serverHandled: false };
  }
}

async function platformCanSyncNow(platform) {
  return (await platformCapability(platform)).canSync;
}

async function listSyncRuns() {
  const response = await SA.api("/v1/sync-runs?limit=200", { timeoutMs: 10000 });
  return response.items || [];
}

function platformSpec(platform) {
  return globalThis.SAPlatformCatalog?.platformCatalogEntry?.(platform) || null;
}

async function waitForTabComplete(tabId, timeoutMs = 45000) {
  const current = await chrome.tabs.get(tabId).catch(() => null);
  if (current?.status === "complete") return current;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("平台页面加载超时"));
    }, timeoutMs);
    function listener(updatedId, changeInfo, tab) {
      if (updatedId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(tab);
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function findExistingPlatformTab(platform, preferredTabId = null) {
  const patterns = SA.patternsForPlatform(platform);
  if (!patterns.length) return null;
  const tabs = await chrome.tabs.query({ url: patterns }).catch(() => []);
  const select = globalThis.SAExtensionUtils?.preferExistingPlatformTab;
  if (typeof select === "function") return select(tabs, preferredTabId);
  return tabs.find(tab => String(tab?.id) === String(preferredTabId)) || tabs.find(tab => tab?.active) || tabs[0] || null;
}

async function sendSyncBatch(syncRunId, body) {
  return SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}/batches`, {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 90000
  });
}

async function syncChromeBookmarks({ accountId = null, syncRunId = null, triggerType = "manual" } = {}) {
  const hasPermission = await chrome.permissions.contains({ permissions: ["bookmarks"] });
  if (!hasPermission) throw new Error("请先授权读取 Chrome 书签");
  let account = null;
  if (accountId) account = (await listAccounts()).find(item => item.id === accountId) || null;
  if (!account) account = (await listAccounts()).find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks") || null;
  if (!account) throw new Error("Chrome 书签账号尚未连接");
  if (!syncRunId) {
    const started = await SA.api(`/v1/accounts/${encodeURIComponent(account.id)}/sync`, {
      method: "POST",
      body: JSON.stringify({ mode: account.last_sync_at ? "incremental" : "first_full", relation_types: ["bookmark"], trigger_type: triggerType }),
      timeoutMs: 15000
    });
    syncRunId = started.sync_run_id;
  }
  const tree = await chrome.bookmarks.getTree();
  const config = await SA.getConfig();
  const records = SAExtensionUtils.flattenBookmarksTree(tree).map(item => ({
    ...item,
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAExtensionUtils.chunk(records, 200);
  for (let index = 0; index < chunks.length; index += 1) {
    const control = await stopStateFor(syncRunId);
    if (control) return { ok: true, accountId: account.id, syncRunId, status: control === "pause" ? "paused" : "cancelled", controlled: true };
    await sendSyncBatch(syncRunId, {
      relation_type: "bookmark",
      scope_type: "collection",
      collection_key: "",
      items: chunks[index],
      completeness: "partial",
      batch_index: index,
      batch_count: chunks.length || 1,
      has_more: index < chunks.length - 1,
      cursor: { source: "chrome.bookmarks", batch_index: index, total_items: records.length }
    });
    await chrome.action.setBadgeBackgroundColor({ color: "#171717" });
    await chrome.action.setBadgeText({ text: `${Math.min(records.length, (index + 1) * 200)}`.slice(-4) });
  }
  const finalControl = await stopStateFor(syncRunId);
  if (finalControl) return { ok: true, accountId: account.id, syncRunId, status: finalControl === "pause" ? "paused" : "cancelled", controlled: true };
  const result = await sendSyncBatch(syncRunId, {
    relation_type: "bookmark",
    scope_type: "relation",
    items: [],
    completeness: "complete",
    batch_index: chunks.length,
    batch_count: chunks.length + 1,
    has_more: false,
    cursor: { source: "chrome.bookmarks", total_items: records.length }
  });
  await chrome.action.setBadgeBackgroundColor({ color: "#1f7a4c" });
  await chrome.action.setBadgeText({ text: "✓" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2500);
  return { ok: true, accountId: account.id, syncRunId, imported: records.length, status: result.status };
}

async function connectChromeBookmarks() {
  const granted = await chrome.permissions.request({ permissions: ["bookmarks"] });
  if (!granted) return { ok: false, state: "unauthorized", error: "你没有授权读取 Chrome 书签" };
  const existing = (await listAccounts()).find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks");
  if (existing) {
    const queued = await enqueueAccountSync({ accountId: existing.id, triggerType: "manual" });
    return { ...queued, state: "connected", message: "Chrome 书签已连接，首次全量同步已进入后台队列" };
  }
  const start = await SA.api("/v1/accounts/connect/start", {
    method: "POST",
    body: JSON.stringify({
      platform: "generic-web", auth_method: "chrome_bookmarks", display_name: "Chrome 书签",
      external_account_id: "chrome-bookmarks", auto_sync_enabled: true, sync_interval_minutes: 360,
      relation_types: ["bookmark"]
    })
  });
  const completed = await SA.api("/v1/accounts/connect/generic-web/complete", {
    method: "POST",
    body: JSON.stringify({
      connection_ref: start.connection_ref,
      external_account_id: "chrome-bookmarks",
      display_name: "Chrome 书签",
      verified: true,
      metadata: { auth_method: "chrome_bookmarks", permission: "bookmarks", auto_sync_enabled: true, sync_interval_minutes: 360 }
    })
  });
  const queued = await enqueueAccountSync({
    accountId: completed.account_id,
    syncRunId: completed.first_sync?.sync_run_id || null,
    triggerType: "first_connect"
  });
  return { ...queued, state: "connected", message: "Chrome 书签已连接，首次全量同步已进入后台队列" };
}

async function connectBrowserPlatform(platform) {
  const spec = platformSpec(platform);
  if (!spec) throw new Error("当前平台尚未配置账号镜像入口");
  const granted = await SA.requestPlatformPermission(platform);
  if (!granted) return { ok: false, state: "unauthorized", error: `未获得${spec.label}页面读取权限` };
  // Reuse a tab from the same persistent Chrome profile whenever possible.
  // It avoids opening a second login journey and preserves the owner-selected page context.
  const existingTab = await findExistingPlatformTab(platform);
  const start = await SA.api("/v1/accounts/connect/start", {
    method: "POST",
    body: JSON.stringify({
      platform, auth_method: "browser_session", display_name: `${spec.label}账号`,
      auto_sync_enabled: true, sync_interval_minutes: 360, relation_types: spec.relations
    }),
    timeoutMs: 15000
  });
  const tab = existingTab || await chrome.tabs.create({ url: spec.home, active: true });
  await setPendingConnection(platform, {
    connectionRef: start.connection_ref,
    authMethod: "browser_session",
    createdAt: Date.now(),
    tabId: tab.id,
    relations: spec.relations
  });
  if (existingTab?.id) {
    await chrome.tabs.update(existingTab.id, { active: true });
  }
  return {
    ok: true,
    state: "authorizing",
    platform,
    tabId: tab.id,
    message: existingTab
      ? `已复用当前${spec.label}页面，正在确认登录态并启动首次同步。`
      : `已在当前 Chrome profile 中打开${spec.label}，插件会检测现有登录态。`
  };
}

async function connectPlatform(platform) {
  if (platform === "generic-web" || platform === "chrome-bookmarks") return connectChromeBookmarks();
  // 西方三源走 Cookie 托管（T06）：读本域会话 → 加密上传 → 服务端跑 gallery-dl / yt-dlp。
  //
  // **这一条先前是缺的**：SA_CONNECT_PLATFORM_SESSION 在 background 里建好了，
  // 却没有任何界面通向它——点「连接 X」会掉进下面那条 browser_session 老路，
  // 而那条路在 T03 拆掉 DOM 抓取之后只会回 LOGIN_PROOF_UNAVAILABLE。
  // 也就是说 T06 整套机制从界面上够不着。在真实浏览器里跑 T05 时才发现。
  if (globalThis.SACookieExport?.ALLOWED_PLATFORMS?.[platform]) {
    return connectPlatformSessionByCookies(platform);
  }
  return connectBrowserPlatform(platform);
}

/** 西方三源的连接入口：申请权限 → 导出会话 → 加密上传。 */
async function connectPlatformSessionByCookies(platform) {
  const spec = globalThis.SACookieExport.ALLOWED_PLATFORMS[platform];
  const origins = spec.domains.flatMap(d => [`https://*.${d}/*`, `https://${d}/*`]);
  const granted = await chrome.permissions.request({ permissions: ["cookies"], origins })
    .catch(() => false);
  if (!granted) {
    return { ok: false, state: "unauthorized", platform,
             failureCode: "PLATFORM_PERMISSION_DENIED",
             error: "没有获得读取该平台登录状态的授权。" };
  }
  const config = await SA.getConfig();
  try {
    const { count } = await globalThis.SACookieExport.connectPlatformSession(platform, {
      endpoint: config.endpoint, token: config.token,
    });
    // 只回条数，永远不回 cookie 的名或值。
    return { ok: true, state: "connected", platform, count,
             message: `已连接，登录状态已加密保存（${count} 条）。随时可以一键撤销。` };
  } catch (error) {
    const code = error?.code || "UPLOAD_FAILED";
    return { ok: false, state: code === "NOT_LOGGED_IN" ? "needs_user_action" : "failed",
             failureCode: code, error: error?.message || "连接失败" };
  }
}

function resolveRelationUrl(platform, relation, profileUrl = "") {
  const spec = platformSpec(platform);
  let url = spec?.relationUrls?.[relation] || spec?.home;
  if (platform === "x" && relation === "like" && /https:\/\/x\.com\/[^/]+/i.test(profileUrl)) url = `${profileUrl.replace(/\/$/, "")}/likes`;
  if (platform === "bilibili" && /space\.bilibili\.com\/\d+/i.test(profileUrl)) {
    const base = profileUrl.match(/https:\/\/space\.bilibili\.com\/\d+/i)?.[0];
    if (relation === "favorite") url = `${base}/favlist`;
    if (relation === "like") url = base;
  }
  return url;
}

async function navigateMirrorTab(tabId, url) {
  await chrome.tabs.update(tabId, { url, active: true });
  await waitForTabComplete(tabId);
}

async function sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult, collectionKey = "", collectionName = "" }) {
  const config = await SA.getConfig();
  const items = (scopeResult.items || []).map(item => ({
    ...item,
    platform,
    relation_type: relation,
    collection_key: collectionKey || item.collection_key || "",
    // 同上：collection_name 只能在批次级别出现（下面 sendSyncBatch 已经带了）。
    // 放到条目上会被 CaptureRequest 的 extra="forbid" 整批打回 422。
    destination_ids: serverDestinations(config)
  }));
  const chunks = SAExtensionUtils.chunk(items, 200);
  for (let index = 0; index < chunks.length; index += 1) {
    await sendSyncBatch(syncRunId, {
      relation_type: relation,
      scope_type: "collection",
      collection_key: collectionKey,
      collection_name: collectionName,
      items: chunks[index],
      completeness: "partial",
      batch_index: index,
      batch_count: chunks.length || 1,
      has_more: index < chunks.length - 1,
      cursor: { ...scopeResult.cursor, batch_index: index, collection_key: collectionKey }
    });
  }
  if (collectionKey) {
    await sendSyncBatch(syncRunId, {
      relation_type: relation,
      scope_type: "collection",
      collection_key: collectionKey,
      collection_name: collectionName,
      items: [],
      completeness: scopeResult.completeness === "complete" ? "complete" : "partial",
      batch_index: chunks.length,
      batch_count: chunks.length + 1,
      has_more: false,
      failure_code: scopeResult.failureCode || null,
      cursor: { ...scopeResult.cursor, collection_key: collectionKey }
    });
  }
  return { imported: items.length, chunks: chunks.length, complete: scopeResult.completeness === "complete" };
}

/** 取数缝隙 —— **T08 只需要换掉这一个函数体**。
 *
 * v0.0.0.6 这里向 content script 发 `SA_MIRROR_SCAN_RELATION`，由 DOM 抓取器
 * 滚页面、抠选择器、凑出列表。那条路已被 CONFLICT_ORDER 实测证伪并随 T03 删除。
 * 替代品（在 Owner 浏览器里拦平台自己的 API 响应）属于 T08。
 *
 * **它现在抛错，而不是返回空列表——这是刻意的。** 返回 `{ ok: true, items: [] }`
 * 会一路走完 sendBrowserScopeBatches，在服务端留下一条 completeness=complete、
 * item_count=0 的扫描回执，也就是 INV-NO-SILENT-ZERO 明令禁止的那种"静默的零"：
 * 界面显示同步成功、库里一条没有、没有任何地方说得出为什么。
 * v0.0.0.6 生产上"永远是 0"就是这么来的（见 evidence/T00/CURRENT_TRUTH.json）。
 *
 * 抛出的错由 runBrowserAccountSync 的 catch 接住，写成
 * completeness=failed + failure_code=ACQUISITION_PATH_NOT_INSTALLED，
 * 用户看到的是"这条没成，原因是什么"，而不是"这条空"。
 */
async function acquireRelationItems({ tabId, platform, relation } = {}) {
  if (platform === "bilibili" && relation === "favorite") {
    return acquireBilibiliFavorites({ tabId });
  }
  const error = new Error("本版本尚未接入平台列表读取通道，请等待版本更新后重试。");
  error.failureCode = "ACQUISITION_PATH_NOT_INSTALLED";
  throw error;
}

/** B 站收藏夹：在**他自己的 B 站标签页里**调 B 站自己的公开接口（v0.0.0.7 / G1）。
 *
 * 取数逻辑全在 content/bilibili-reader.js，那份文件可以在 Node 里直接跑
 * （它同时挂 globalThis 和 module.exports），所以判据能打真实接口去验它，
 * 而不是验一份我自己写的、和实现共用同一套假设的固定装置。
 *
 * **为什么必须在标签页里跑，不能在 service worker 里跑：**
 * worker 发出去的请求源是 `chrome-extension://…`，而 B 站的 CORS 只回显
 * 它自己的子域（2026-08-06 实测：Origin 为 www / space.bilibili.com 时
 * 回 `access-control-allow-origin` 同源 + `allow-credentials: true`）。
 * 更要紧的是 INV-DOMESTIC-COOKIE-STAYS：在页面里发请求，带凭据的是浏览器本身，
 * 这段代码从头到尾没有读过、存过、传过任何 cookie 的名或值。
 */
async function acquireBilibiliFavorites({ tabId }) {
  if (!Number.isInteger(tabId)) {
    const error = new Error("没有可用的 B 站页面。");
    error.failureCode = "BILIBILI_TAB_UNAVAILABLE";
    throw error;
  }
  // 先要权限再注入：executeScript 缺 host 权限时抛的异常和「注入失败」长得一样，
  // 而这两件事的下一步完全不同（一个是点一下授权，一个是真的坏了）。
  const granted = await SA.requestPlatformPermission("bilibili").catch(() => false);
  if (!granted) {
    const error = new Error("没有获得读取 B 站页面的授权，无法同步收藏夹。");
    error.failureCode = "PLATFORM_PERMISSION_DENIED";
    throw error;
  }
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  // **必须确认这个标签页真的停在 bilibili.com 上。** 不在的话请求源不对，
  // B 站的 CORS 会拒，报出来的错会指向一个完全不相干的方向。
  if (!/^https:\/\/([a-z0-9-]+\.)*bilibili\.com\//i.test(String(tab?.url || ""))) {
    const error = new Error("当前页面不在 B 站上，没法用你的登录态读收藏夹。");
    error.failureCode = "BILIBILI_TAB_NOT_ON_PLATFORM";
    throw error;
  }
  await chrome.scripting.executeScript({
    target: { tabId }, files: ["content/bilibili-reader.js"],
  });
  const injected = await chrome.scripting.executeScript({
    target: { tabId },
    // executeScript 会 await 返回的 Promise，所以这里直接把结果交出去。
    func: () => globalThis.SABilibiliReader.readAllFavorites(),
  });
  const result = injected?.[0]?.result;
  if (!result || typeof result !== "object") {
    const error = new Error("读取 B 站收藏夹没有返回结果。");
    error.failureCode = "BILIBILI_NO_RESULT";
    throw error;
  }
  if (!result.ok) {
    // **读不到就报读不到。** 绝不 return { ok:true, items: [] } —— 那会在服务端
    // 留下一条 completeness=complete / item_count=0 的回执，也就是
    // INV-NO-SILENT-ZERO 禁止的那种零：界面显示同步成功、库里一条没有。
    const error = new Error(result.error || "读取 B 站收藏夹失败。");
    error.failureCode = result.failureCode || "BILIBILI_READ_FAILED";
    throw error;
  }
  return {
    ok: true,
    items: result.items || [],
    completeness: result.completeness || "partial",
    failureCode: result.failureCode || null,
    completionReason: result.completionReason || null,
    cursor: result.cursor || {},
  };
}

async function scanBrowserScope({ tabId, platform, relation, syncRunId, url, collectionKey = "", collectionName = "", alreadyLoaded = false }) {
  if (!alreadyLoaded) await navigateMirrorTab(tabId, url);
  // 取数与传输是两件事，缝在这一行上：上面换实现，下面这两句不动。
  const result = await acquireRelationItems({ tabId, platform, relation, syncRunId, collectionKey, collectionName });
  if (result?.controlled) return { controlled: true, status: result.controlAction === "pause" ? "paused" : "cancelled", relation };
  if (!result?.ok) throw new Error(result?.error || "平台列表读取失败");
  const sent = await sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult: result, collectionKey, collectionName });
  return { ...result, ...sent, collectionKey, collectionName, url };
}

async function scanOneBrowserRelation({ tabId, platform, relation, syncRunId, profileUrl = "" }) {
  const url = resolveRelationUrl(platform, relation, profileUrl);
  if (!url) {
    return sendSyncBatch(syncRunId, {
      relation_type: relation, scope_type: "relation", items: [], completeness: "failed",
      failure_code: "RELATION_URL_UNAVAILABLE", has_more: false
    });
  }
  await navigateMirrorTab(tabId, url);
  // v0.0.0.7 / T03：收藏夹枚举原先由 DOM 抓取器扫页面里的链接文字猜出来
  // （靠一张"看着像收藏夹"的中文文案正则表）。
  // 抓取器已删。T08 从平台自己的 API 响应里拿收藏夹清单——那是权威来源，
  // 不是从界面文案反推。在那之前这里为空，且下面的取数缝隙会明确报错，
  // 不会出现"收藏夹 0 个但同步成功"。
  const discoveredCollections = [];

  const scopeResults = [];
  const baseResult = await scanBrowserScope({ tabId, platform, relation, syncRunId, url, alreadyLoaded: true });
  if (baseResult?.controlled) return baseResult;
  scopeResults.push(baseResult);

  const seenUrls = new Set([SAExtensionUtils.canonicalUrl(url)]);
  for (const collection of discoveredCollections.slice(0, 100)) {
    const collectionUrl = SAExtensionUtils.canonicalUrl(collection.url);
    if (!collectionUrl || seenUrls.has(collectionUrl)) continue;
    seenUrls.add(collectionUrl);
    const control = await stopStateFor(syncRunId);
    if (control) return { controlled: true, status: control === "pause" ? "paused" : "cancelled", relation };
    const collectionResult = await scanBrowserScope({
      tabId,
      platform,
      relation,
      syncRunId,
      url: collectionUrl,
      collectionKey: String(collection.collectionKey || collectionUrl).slice(0, 512),
      collectionName: String(collection.collectionName || "未命名收藏夹").slice(0, 256)
    });
    if (collectionResult?.controlled) return collectionResult;
    scopeResults.push(collectionResult);
  }

  const allComplete = scopeResults.length > 0 && scopeResults.every(item => item.completeness === "complete");
  const imported = scopeResults.reduce((sum, item) => sum + Number(item.imported || 0), 0);
  const failureCodes = scopeResults.map(item => item.failureCode).filter(Boolean);
  return sendSyncBatch(syncRunId, {
    relation_type: relation,
    scope_type: "relation",
    items: [],
    completeness: allComplete ? "complete" : "partial",
    batch_index: scopeResults.length,
    batch_count: scopeResults.length + 1,
    has_more: false,
    failure_code: allComplete ? null : (failureCodes[0] || "RELATION_TERMINAL_NOT_PROVEN"),
    cursor: {
      relation_url: url,
      // 收藏夹个数优先取**取数器自己数出来的那个**。
      // `scopeResults.length - 1` 只在「一个收藏夹跑一个 scope」的形态下才对；
      // B 站这条路是一个 scope 里读完全部收藏夹、每条自带 collection_key，
      // 于是那个减法恒等于 0——**明明读了 7 个收藏夹，回执上写着 0 个**。
      discovered_collections: Number(
        baseResult?.cursor?.collections_found ?? Math.max(0, scopeResults.length - 1)),
      imported_items: imported,
      scope_completion: scopeResults.map(item => ({
        collection_key: item.collectionKey || "",
        complete: item.completeness === "complete",
        reason: item.completionReason || item.failureCode || null,
        observed_count: item.cursor?.observed_count ?? item.imported ?? 0
      }))
    }
  });
}

async function runBrowserAccountSync({ account, syncRunId = null, tabId = null, profileUrl = "", triggerType = "manual" }) {
  const spec = platformSpec(account.platform);
  if (!spec) throw new Error("该平台暂不支持浏览器账号同步");
  // **在碰任何标签页之前先拦。** 入队那一层已经滤过一次，这里是第二道：
  // 队列里可能还留着旧任务（chrome.storage 里的），它们不该再去抢标签页。
  const capability = await platformCapability(account.platform);
  // **顺序和 syncAccountById 一样：先问「同步得动吗」，再问「谁来干」。**
  //
  // 这里原来是反的——先看 serverHandled，交给服务端。理由写着「抛错会写成
  // 一次 completeness=failed，用户什么都没做错」。**那个理由对，顺序错。**
  //
  // 当初的例子是 bilibili：它同时 server_handled=true 和 sync_supported=false。
  // 走到这条路的是 chrome.storage 里压着的升级前旧任务；先看 serverHandled
  // 就把它交给服务端，而服务端对它同样没有能用的取数实现——那次 run 停在半路，
  // **界面一直转圈**。而隔壁 syncAccountById 的注释早就写明了这一点：
  // 「服务端登记了这个平台」不等于「服务端做得成」。
  //
  // **2026-08-06 / G1：bilibili 现在走的是本函数下面的浏览器路。**
  // 规矩没变，只是例子换成了 x / reddit / instagram。
  //
  // 先判 canSync 并不引入新失败码：ACQUISITION_PATH_NOT_INSTALLED 是既有的，
  // 冻结词典里有对应句子，隔壁那条路用的就是它。**一次说得清的失败，
  // 比一个永远转圈的界面好。**
  if (!capability.canSync) {
    const error = new Error("本版本还不能自动读取这个平台的收藏列表，已停止，不会反复重试。");
    error.failureCode = "ACQUISITION_PATH_NOT_INSTALLED";
    throw error;
  }
  if (capability.serverHandled) {
    // 走到这里说明有人绕过了 syncAccountById 的分流——最常见的是
    // chrome.storage 里压着一条**升级前**入队的旧任务。
    // 这个平台确实同步得动，只是该由服务端干，所以交过去，不抛错。
    return startServerSideSync(account.id, triggerType);
  }
  // **扫描范围要用「这一版真的读得到的关系」，不是「这个平台声明的关系」。**
  //
  // B 站声明四种（收藏夹/稍后再看/历史/点赞），而 G1 只做出了收藏夹那条取数路。
  // 照 spec.relations 循环的话，一次同步跑四轮、后三轮各抛一次
  // ACQUISITION_PATH_NOT_INSTALLED，整个 run 停在非完成态——
  // **他要的那件事（收藏夹）其实成了，界面却给他一个失败的同步。**
  //
  // 这也必须同步告诉服务端：relation_scope 里留着读不到的关系，
  // 那次 run 永远等不齐所有关系的终结批次，状态就一直不会收敛。
  const scannable = globalThis.SAPlatformCatalog?.scannableRelations?.(account.platform)
    || spec.relations;
  if (!Array.isArray(scannable) || scannable.length === 0) {
    const error = new Error("本版本没有这个平台可枚举的关系类型。");
    error.failureCode = "ACQUISITION_PATH_NOT_INSTALLED";
    throw error;
  }
  if (!syncRunId) {
    const started = await SA.api(`/v1/accounts/${encodeURIComponent(account.id)}/sync`, {
      method: "POST",
      body: JSON.stringify({ mode: account.last_sync_at ? "incremental" : "first_full", relation_types: scannable, trigger_type: triggerType }),
      timeoutMs: 15000
    });
    syncRunId = started.sync_run_id;
  }
  let tab = tabId ? await chrome.tabs.get(tabId).catch(() => null) : null;
  if (!tab) tab = await chrome.tabs.create({ url: spec.home, active: true });
  const results = [];
  for (let index = 0; index < scannable.length; index += 1) {
    const relation = scannable[index];
    try {
      const relationResult = await scanOneBrowserRelation({ tabId: tab.id, platform: account.platform, relation, syncRunId, profileUrl });
      results.push(relationResult);
      if (relationResult?.controlled) break;
    } catch (error) {
      const control = await stopStateFor(syncRunId);
      if (control) {
        results.push({ controlled: true, status: control === "pause" ? "paused" : "cancelled", relation });
        break;
      }
      results.push(await sendSyncBatch(syncRunId, {
        relation_type: relation,
        scope_type: "relation",
        items: [],
        completeness: "failed",
        // 带了具体原因就报具体原因。一律报 BROWSER_SCAN_FAILED 会把
        // "本版本没接取数通道"和"这次扫描炸了"混成同一条，
        // 用户和 T14 的文案矩阵都分不出该怎么办。
        failure_code: error?.failureCode || "BROWSER_SCAN_FAILED",
        cursor: { error: String(error?.message || error).slice(0, 300) },
        has_more: false
      }));
    }
    await chrome.action.setBadgeBackgroundColor({ color: "#171717" });
    // 分母也要用 scannable：用 spec.relations 的话，B 站读完唯一那条会显示 "1/4"，
    // badge 停在 1/4 看起来像卡住了，而它其实已经做完了。
    await chrome.action.setBadgeText({ text: `${index + 1}/${scannable.length}` });
  }
  const latest = await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}`, { timeoutMs: 10000 });
  await chrome.action.setBadgeBackgroundColor({ color: latest.status === "completed" ? "#1f7a4c" : "#9a6700" });
  await chrome.action.setBadgeText({ text: latest.status === "completed" ? "✓" : "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 3000);
  return { ok: true, syncRunId, status: latest.status, results };
}

// v0.0.0.7 / T03 收尾：这里原先是 completePendingBrowserConnection —— 由内容脚本
// 发 SA_PLATFORM_PAGE_READY 触发，凭页面上的登录迹象把账号标记为已连接。
// **整段删除。**
//
// 它的触发条件在 T03 删掉 DOM 抓取器之后就再也不会成立：没有任何脚本发那条消息，
// 而它读的 message.loggedIn / externalAccountId / accountName 三个字段在全仓
// 无人产出。真正的登录态确认在 verifyPendingPlatform 里，那里明确返回
// LOGIN_PROOF_UNAVAILABLE 并说清楚原因——那是诚实的阻塞，这段是它的残骸。
//
// 留着的坏处不是占地方：它让「浏览器会话连接」在代码上看起来是完整的一条闭环，
// 而实际上中间那一环不存在。本轮反复栽的就是这种「看着接上了」。
async function verifyPendingPlatform(platform) {
  const pending = (await getPendingConnections())[platform];
  if (!pending) return { ok: false, state: "not_pending", error: "没有等待确认的连接流程，请重新点击连接账号" };
  const preferred = await findExistingPlatformTab(platform, pending.tabId);
  if (!preferred?.id) {
    return { ok: false, state: "authorizing", error: "未找到可复用的平台页面；插件不会打开新的登录页。" };
  }
  await chrome.tabs.update(preferred.id, { active: true });
  // v0.0.0.7 / T03：登录态确认原先靠扫页面上有没有"登录"按钮、有没有头像元素。
  // 那是 DOM 抓取，已删。
  //
  // 这里**不能退回"猜它已登录"**：猜错的后果是拿一个未登录的会话去发起首次全量同步，
  // 平台返回空列表，系统记一条"同步完成、0 条"——又是 INV-NO-SILENT-ZERO 那个洞。
  //
  // **2026-08-06 / G1：B 站这条有可证的信号了。**
  // 上面那段原话写着「T08 的拦截路会用『是否收到过带身份的 API 响应』来确认，
  // 那是可证的信号」——而 bilibili-reader.js 的 currentUser() 正是它：
  // 直接问 B 站 `/x/web-interface/nav`，回 isLogin + mid + uname。
  // 这比"收到过带身份的响应"还硬一档：身份是**平台自己说的**，
  // 而且顺带给出真实的账号标识，不必再拿占位符去建账号。
  if (platform === "bilibili") return verifyBilibiliSession(pending, preferred.id);
  return {
    ok: false,
    state: "authorizing",
    failureCode: "LOGIN_PROOF_UNAVAILABLE",
    error: "本版本无法确认这个页面的登录态，账号暂不能连接；请等待版本更新后重试。"
  };
}

/** 确认 B 站登录态，确认得了就把账号真的建起来（v0.0.0.7 / G1）。
 *
 * 这一步不做的话，G1 那条取数路对 Owner 来说是**够不着的**：
 * 点「连接 B 站」→ 拿到 LOGIN_PROOF_UNAVAILABLE → 账号建不起来 →
 * 没有账号就没有同步 → 收藏夹读得再好也没人调它。
 */
async function verifyBilibiliSession(pending, tabId) {
  let who;
  try {
    await chrome.scripting.executeScript({
      target: { tabId }, files: ["content/bilibili-reader.js"],
    });
    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => globalThis.SABilibiliReader.currentUser(),
    });
    who = injected?.[0]?.result;
  } catch (error) {
    return { ok: false, state: "authorizing", failureCode: "BILIBILI_TAB_NOT_ON_PLATFORM",
             error: "没能在这个 B 站页面上确认登录态，请停在 B 站页面再点一次。" };
  }
  if (!who?.ok) {
    // **没登录就说没登录，不要建账号。** 建了的话下一步就是拿一个空会话
    // 去跑首次全量同步，然后记一条「同步完成、0 条」——INV-NO-SILENT-ZERO。
    return {
      ok: false, state: "needs_user_action",
      failureCode: who?.failureCode || "BILIBILI_NOT_LOGGED_IN",
      error: who?.error || "还没在这个浏览器里登录 B 站。请在这个页面登录，然后再点一次「连接账号」。",
    };
  }
  const displayName = who.name ? `B站 · ${who.name}` : "B站账号";
  const completed = await SA.api("/v1/accounts/connect/bilibili/complete", {
    method: "POST",
    body: JSON.stringify({
      connection_ref: pending.connectionRef,
      // 账号标识用 B 站自己的 mid —— 换个昵称、换台机器都还是同一个账号。
      external_account_id: String(who.mid),
      display_name: displayName,
      verified: true,
      // **这里一个字都不许沾凭据。** 服务端 _safe_account_metadata 会把带
      // cookie/token/password/auth_header 字样的键整个打回 422，而那是对的：
      // 账号元数据会进运行日志。这里只写"是怎么确认的"，不写"用什么确认的"。
      metadata: {
        auth_method: "browser_session",
        verified_by: "bilibili_nav_api",
        auto_sync_enabled: true,
        sync_interval_minutes: 360,
      },
    }),
    timeoutMs: 15000,
  });
  await setPendingConnection("bilibili", null);
  const queued = await enqueueAccountSync({
    accountId: completed.account_id,
    syncRunId: completed.first_sync?.sync_run_id || null,
    triggerType: "first_connect",
  });
  return {
    ...queued, ok: true, state: "connected", platform: "bilibili",
    accountId: completed.account_id, displayName,
    message: `已确认登录（${displayName}），正在后台读取你的收藏夹。`,
  };
}

async function syncAccountById(accountId, options = {}) {
  const account = (await listAccounts()).find(item => item.id === accountId);
  if (!account) throw new Error("账号不存在");
  if (account.platform === "generic-web" && account.external_account_id === "chrome-bookmarks") {
    return syncChromeBookmarks({
      accountId,
      syncRunId: options.syncRunId || null,
      triggerType: options.triggerType || "manual"
    });
  }
  // **服务端自己就能取的平台，一个标签页都不该碰。**
  //
  // 实测（2026-08-04，真 Chrome）：对 x 跑一次 runBrowserAccountSync，
  // 用户的标签页被抢了 2 次——先导到 x.com/i/bookmarks，再导到 x.com/home，
  // 两次都是 active: true（切到前台）。而 x 在服务端的
  // SERVER_ACCOUNT_CONNECTORS 里，本来就不需要浏览器参与。
  //
  // 上一轮修的是「服务端说同步不了」的平台；这一条修的是
  // 「服务端自己就能干」的平台。同一个抱怨的另一半。
  const capability = await platformCapability(account.platform);
  // **顺序要紧：先问「同步得动吗」，再问「谁来干」。**
  //
  // 这条规矩当初是被 bilibili 逼出来的：它曾经同时 server_handled=true
  // （在 SERVER_ACCOUNT_CONNECTORS 里）**和** sync_supported=false
  // （不在 SYNCABLE_NOW 里）。先看 serverHandled 就会把它交给服务端，
  // 而服务端对它同样没有能用的取数实现——那次 run 停在半路，界面一直转圈。
  //
  // **2026-08-06 / G1：bilibili 已经不是这个例子了。** 它现在
  // sync_supported=true、server_handled=false，走的是下面的浏览器路
  // （acquireBilibiliFavorites）。之所以把这段历史留着，是因为**规矩仍然成立**：
  // 「服务端登记了这个平台」不等于「服务端做得成」，x / reddit / instagram
  // 三个现在就是这个形状。
  if (!capability.canSync) {
    const error = new Error("本版本还不能自动读取这个平台的收藏列表，已停止，不会反复重试。");
    error.failureCode = "ACQUISITION_PATH_NOT_INSTALLED";
    throw error;
  }
  if (capability.serverHandled) {
    return startServerSideSync(accountId, options.triggerType || "manual");
  }
  return runBrowserAccountSync({
    account,
    syncRunId: options.syncRunId || null,
    tabId: options.tabId || null,
    profileUrl: options.profileUrl || "",
    triggerType: options.triggerType || "manual"
  });
}

async function syncAllAccounts(triggerType = "manual") {
  return enqueueAllAccounts(triggerType);
}

async function openAccountCenter() {
  await chrome.tabs.create({ url: chrome.runtime.getURL("options.html#platforms") });
  return { ok: true };
}

async function scheduleBookmarkRefresh() {
  const hasPermission = await chrome.permissions.contains({ permissions: ["bookmarks"] });
  if (!hasPermission) return;
  await chrome.alarms.create("sa-bookmarks-refresh", { delayInMinutes: 0.2 });
}

chrome.runtime.onInstalled.addListener(async details => {
  const config = await SA.setConfig({});
  await ensureMenus();
  await chrome.alarms.create("sa-account-sync", { periodInMinutes: 360 });
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  if (details.reason === "install" || details.reason === "update") {
    await reconnectOpenPwaBridgeTabs();
  }
  if (details.reason === "install" && !config.onboardingComplete) {
    await chrome.tabs.create({ url: chrome.runtime.getURL("options.html?onboarding=1") });
  }
});

chrome.runtime.onStartup.addListener(() => {
  ensureMenus().catch(() => {});
  chrome.alarms.create("sa-account-sync", { periodInMinutes: 360 }).catch(() => {});
  getSyncQueue().then(queue => queue.length ? scheduleSyncQueue() : null).catch(() => {});
});

// **每次 service worker 启动都要收残局，不能只挂在 onStartup 上。**
// onStartup 只在**浏览器**启动时触发一次；而 MV3 的 worker 空闲约 30 秒
// 就被回收、来事件再拉起，一天里能重启几十次。上一次同步如果是在
// worker 被杀时中断的，那些残局只有在这里才收得到。
//
// 模块作用域在每次 worker 启动时重新求值——这是 MV3 里唯一的
// 「worker 起来了」钩子。
reclaimAbandonedSyncWork()
  .then(state => (state.queued ? scheduleSyncQueue() : null))
  .catch(() => {});
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") injectFabIfAuthorized(tabId, tab.url).catch(() => {});
});
chrome.permissions.onAdded.addListener(async () => {
  try { const tab = await SA.activeTab(); await injectFabIfAuthorized(tab.id, tab.url); } catch (_) {}
});
// 标签页没了，那一页的观察器自报也就没有意义了。不清会随着开关标签页无限增长。
chrome.tabs.onRemoved.addListener(tabId => { observerStateByTab.delete(tabId); });


chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "sa-bookmarks-refresh") {
    listAccounts().then(accounts => {
      const account = accounts.find(item => item.platform === "generic-web" && item.external_account_id === "chrome-bookmarks");
      return account ? enqueueAccountSync({ accountId: account.id, triggerType: "bookmark_change" }) : null;
    }).catch(() => {});
  }
  if (alarm.name === "sa-account-sync") enqueueAllAccounts("scheduled").catch(() => {});
  if (alarm.name === SYNC_QUEUE_ALARM) processSyncQueue().catch(() => {});
});

if (chrome.bookmarks) {
  chrome.bookmarks.onCreated.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onChanged.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onMoved.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
  chrome.bookmarks.onRemoved.addListener(() => scheduleBookmarkRefresh().catch(() => {}));
}

chrome.commands.onCommand.addListener(async command => {
  try {
    if (command === "save-current-page") {
      await captureActive({ mode: "page", source: "keyboard_shortcut" });
      return;
    }
    if (command === "open-task-center") {
      const tab = await SA.activeTab().catch(() => null);
      if (tab?.windowId) await chrome.sidePanel.open({ windowId: tab.windowId });
    }
  } catch (_) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2200);
  }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id || !tab.url) return;
  try {
    if (info.menuItemId === MENU_SELECTION && info.selectionText) {
      const config = await SA.getConfig();
      await captureRecord({ url: tab.url, title: tab.title, text: info.selectionText, media_urls: [], raw_metadata: { source: "selection" } }, tab.url, config, { source: "context_selection" });
    } else if (info.menuItemId === MENU_SAVE) {
      await captureActive({ mode: "page", source: "context_menu" }, tab);
    }
    await chrome.action.setBadgeBackgroundColor({ color: "#1f7a4c" });
    await chrome.action.setBadgeText({ text: "✓" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }).catch(() => {}), 2200);
  } catch (_) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message?.type === "SA_ACCOUNT_CONNECT") return connectPlatform(String(message.platform || ""));
    if (message?.type === "SA_VERIFY_PLATFORM_SESSION") return verifyPendingPlatform(String(message.platform || ""));
    if (message?.type === "SA_GET_PENDING_CONNECTIONS") return { ok: true, items: await getPendingConnections() };
    if (message?.type === "SA_OPEN_ACCOUNT_CENTER") return openAccountCenter();
    if (message?.type === "SA_SYNC_ACCOUNT") return enqueueAccountSync({ accountId: String(message.accountId || ""), triggerType: "manual" });
    if (message?.type === "SA_SYNC_ALL_ACCOUNTS") return syncAllAccounts("manual");
    if (message?.type === "SA_CONTROL_SYNC_RUN") return controlSyncRun({
      syncRunId: String(message.syncRunId || ""),
      accountId: message.accountId ? String(message.accountId) : null,
      action: String(message.action || "")
    });
    // 删除：SA_GET_SYNC_CONTROL_STATE（读一次暂停/取消标记）。全仓没有发送方。
    // 暂停/取消真正生效的路是编排层每一轮自己查 stopStateFor()，那条还在。
    if (message?.type === "SA_CAPTURE_ACTIVE") return captureActive(message, sender?.tab);
    if (message?.type === "SA_OPEN_TASK_CENTER") {
      const tab = await SA.activeTab().catch(() => null);
      if (tab?.windowId) await chrome.sidePanel.open({ windowId: tab.windowId });
      return { ok: true };
    }
    // 删除：SA_REFRESH_FAB（手动重注浮动按钮）。全仓没有发送方，
    // 而 tabs.onUpdated / onActivated 已经在注了。
    if (message?.type === "SA_WEB_BRIDGE_STATUS") {
      const config = await SA.getConfig();
      // 就绪与否只有一个判据：拿现有令牌真的调一次受保护接口。
      // 旧实现先问服务端「还要不要配对」，那条路已随 T03 删除；
      // 而且它把"服务说不用配对"当成"我连得上"——两回事，中间隔着令牌有没有效。
      let paired = false;
      try {
        if (config.token) {
          await SA.api("/v1/extension/bootstrap", { timeoutMs: 5000 });
          paired = true;
        }
      } catch (_) {
        paired = false;
      }
      return {
        detected: true,
        paired,
        configured: Boolean(config.endpoint),
        endpoint: config.endpoint,
        libraryUrl: config.libraryUrl,
        serviceReady: paired,
        version: chrome.runtime.getManifest().version
      };
    }
    // 这里原先是 SA_WEB_BRIDGE_CONFIGURE：把页面下发的 endpoint / libraryUrl
    // 写进扩展配置。**连同 bridge.js 里那条转发一起删除。**
    // 理由见下面 SA_WEB_BRIDGE_ADOPT_TOKEN 的注释——同一个文件里写着
    //「不接受页面下发」，上面却留着一个接受页面下发的入口。
    // 取代旧的一次性码流程（v0.0.0.7 / T03）。
    //
    // 旧流程：服务端生成一串码 → 用户从终端/邮件里找到它 → 手抄进扩展设置页 →
    // 十分钟内没抄完就重来。实际使用中连续失败三次，且"手抄一串字符"本身
    // 就是 INV-ZERO-BARRIER 明令禁止的门槛。
    //
    // 新流程：**已登录的档案馆页面**用自己的会话 cookie 调
    // POST /v1/auth/extension-token 换一个长期可撤销令牌，通过 bridge 直接交给扩展。
    // 用户点一下"连接插件"，不接触令牌文本，一个字符都不用输入。
    //
    // 令牌明文只在页面到扩展这一跳里出现，服务端只存哈希；
    // 撤销后扩展上行立刻 401（T03 的 Oracle）。
    if (message?.type === "SA_WEB_BRIDGE_ADOPT_TOKEN") {
      const current = await SA.getConfig();
      // 服务地址取扩展自己的托管配置，不接受页面下发——页面能改端点就等于
      // 任何拿到桥的页面都能把上行改到别处去。
      const endpoint = String(current.endpoint || "").replace(/\/$/, "");
      const token = String(message.token || "").trim();
      if (!/^https?:\/\//i.test(endpoint)) throw new Error("服务地址无效");
      if (!token) throw new Error("没有收到访问凭据，请在档案馆页面重新点击连接插件。");
      const next = await SA.setConfig({
        endpoint,
        // **页面给的 libraryUrl 只在与端点同源时才收。**
        //
        // 上面那条规则写着「服务地址不接受页面下发」，而这一行原本是
        // `message.libraryUrl || current.libraryUrl`——页面给什么就用什么。
        // 二十行外的注释还记着：`SA_WEB_BRIDGE_CONFIGURE` 被整条删除，
        // 正是因为它「让页面下发 endpoint 与 libraryUrl 写进扩展配置」。
        // **那次删掉了 endpoint 那一半，libraryUrl 这一半原样留在了隔壁。**
        //
        // 2026-08-05 的桥边界演练实测：页面发一条 SA_ADOPT_TOKEN 夹带
        // libraryUrl，端点纹丝不动（那条守住了），而 libraryUrl 被改成了
        // 页面指定的地址。它是「打开档案馆」那颗按钮的去处——用户点它时
        // 认为那是自己的档案馆。
        //
        // 同源才收：真档案馆页面发的就是它自己的地址，天然同源；
        // 别处发来的一律退回扩展自己那份。
        libraryUrl: (() => {
          const offered = String(message.libraryUrl || "").replace(/\/$/, "");
          if (!offered) return current.libraryUrl;
          try {
            if (new URL(offered).origin === new URL(endpoint).origin) return offered;
          } catch (_) { /* 不是合法地址就退回 */ }
          return current.libraryUrl;
        })(),
        token,
        onboardingComplete: true
      });
      // 存下就算数是不够的——立刻用它调一次受保护接口，确认它真的能用。
      // 否则"已连接"会在第一次同步时才被证伪。
      try {
        await SA.api("/v1/extension/bootstrap", { timeoutMs: 8000 });
      } catch (error) {
        await SA.setConfig({ token: "" });
        throw new Error("凭据未能通过验证，请在档案馆页面重新点击连接插件。");
      }
      return { ok: true, paired: true, endpoint: next.endpoint, libraryUrl: next.libraryUrl };
    }
    // 国内三源：装 MAIN world 观察器（v0.0.0.7 / T08）。
    //
    // 硬边界：只包 fetch / XHR 抄一份响应，绝不合成请求、绝不改请求或响应、
    // 绝不读 Cookie。签名（小红书 x-s/x-t、抖音 a_bogus）全由页面自己完成。
    // 国内平台的 Cookie 一步都不出浏览器（INV-DOMESTIC-COOKIE-STAYS）。
    if (message?.type === "SA_INSTALL_NET_OBSERVER") {
      return installNetObserverForTab({
        platform: String(message.platform || "").trim().toLowerCase(),
        tabId: Number(message.tabId),
        diagnostic: message.diagnostic === true,
      });
    }
    // 观察器抄回来的原始响应。**服务端负责解析**——这里只搬运，不 JSON.parse：
    // 解析失败会吞掉本来能救的数据（预制件的原话）。
    if (message?.type === "SA_NET_CAPTURE") {
      const body = String(message.body || "");
      if (!body) return { ok: false, ignored: true };
      netCaptureBuffer.push({
        url: String(message.url || ""), status: Number(message.status || 0),
        body, capturedAt: String(message.capturedAt || ""),
      });
      // 满了之后**丢新的、留早的**，并且把丢掉的条数记下来。
      //
      // 原来是 shift() 丢最早的那条。方向正好反了：收藏列表那个请求是
      // 页面加载时打的，**它永远是最早的那几条之一**；而后面涌进来的是
      // 心跳、埋点、图片信息之类的噪声。丢最早的等于专门丢掉唯一有用的那条，
      // 而且丢得悄无声息——用户看到的是「拦到 200 条，0 条读得懂」。
      if (netCaptureBuffer.length > NET_CAPTURE_LIMIT) {
        netCaptureBuffer.pop();
        netCapturesDropped += 1;
      }
      return { ok: true, buffered: netCaptureBuffer.length };
    }
    if (message?.type === "SA_NET_OBSERVER_STATE") {
      const tabId = Number(sender?.tab?.id);
      if (!Number.isInteger(tabId)) return { ok: false, ignored: true };
      const previous = observerStateByTab.get(tabId) || {};
      observerStateByTab.set(tabId, {
        installed: previous.installed || message.state === "SA_OBSERVER_INSTALLED",
        ready: previous.ready || message.state === "SA_OBSERVER_READY",
        prefixCount: Number(message.prefixCount || previous.prefixCount || 0),
      });
      return { ok: true };
    }
    /** 把抓到的响应真的读一遍——**「拦到了」和「读得懂」是两件事**。
     *
     * 诊断按钮原来只回报地址与字节数。那回答的是「有没有拦到」，
     * 而 Owner 真正要知道的是「拦到的东西我们能不能用」。
     *
     * 2026-08-04 实测（纯 curl 无 Cookie）：B 站收藏接口在没登录时返回
     * HTTP 200 + `{"code":0,"message":"OK","ttl":1,"data":null}`。
     * 只看地址与字节数的话，这一条**看起来完全成功**。
     *
     * 解析在服务端做（响应体原样送过去，这里不 JSON.parse），
     * 服务端要么给条目、要么给失败码 + 一句能照着做的中文。
     */
    if (message?.type === "SA_PARSE_NET_CAPTURES") {
      const platform = String(message.platform || "").trim().toLowerCase();
      if (!netCaptureBuffer.length) {
        return { ok: false, readable: 0, total: 0,
                 failureCode: "NOTHING_CAPTURED",
                 message_zh: "一条响应都没拦到，没有可读的东西。" };
      }
      // **先收敛要送出去的条数，再逐条问服务端。**
      //
      // 诊断模式的前缀是从域名推的（比如 bilibili.com），于是页面上**每一个**
      // 请求都会被抓——心跳、埋点、推荐列表。真实收藏夹页跑满 200 条毫不费力。
      // 而这里是「一条一个 HTTP 往返、每条 20 秒超时、还要把响应体整个传上去」，
      // 200 条就是几分钟的卡死，外加 200 份响应体上传。
      // **Owner 只按一次，卡在那里的话他不知道是没坏还是坏了。**
      //
      // 收敛两步，两步都不静默：
      //   1. 按「去掉查询串的地址」去重——页面反复轮询的是同一个接口，
      //      而收藏列表那个地址是独一份的，去重不会把它去掉。
      //   2. 去重之后仍然封顶 30 条，**取最早的**——收藏列表那个请求是
      //      页面加载时打的，永远在最早的那几条里。
      const seenUrls = new Set();
      const deduped = [];
      for (const capture of netCaptureBuffer) {
        const key = String(capture.url || "").split("?")[0];
        if (seenUrls.has(key)) continue;
        seenUrls.add(key);
        deduped.push(capture);
      }
      const PARSE_LIMIT = 30;
      const toParse = deduped.slice(0, PARSE_LIMIT);
      const notParsed = netCaptureBuffer.length - toParse.length;

      let readable = 0;
      let items = 0;
      let firstProblem = null;
      const readableUrls = [];
      for (const capture of toParse) {
        const parsed = await SA.api("/v1/extension/captures/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform, url: capture.url, body: capture.body }),
          timeoutMs: 20000,
        }).catch(error => ({ ok: false, failure_code: "SERVER_UNREACHABLE",
                             message_zh: error?.message || "连不上你的档案馆。" }));
        if (parsed?.ok) {
          readable += 1;
          items += (parsed.items || []).length;
          // **记下是哪一条读得懂的。**
          //
          // 只报一个「readable=3」的数字，等于报了「有三条能读」却不说是哪三条——
          // 而 T09（抓到即固化）要的恰恰是那个地址：拦截前缀就是从它身上取的。
          // Owner 只按一次诊断；报告里少了这一样，那一按就白按，还得再按一次。
          //
          // 送出去的仍然只有地址，**响应体一个字节都不上传**。
          readableUrls.push(capture.url);
        } else if (!firstProblem) firstProblem = parsed;
      }
      // **丢掉的条数要说出来。** 上限本身没问题，悄悄触顶才有问题——
      // 那会让「缓冲区满了、有用的那条没进来」看起来和「平台没发这个请求」一模一样。
      const dropped = netCapturesDropped;
      const notes = [];
      if (dropped > 0) notes.push(`另有 ${dropped} 条因为太多没收下`);
      // **没读的那些也要说出来。** 悄悄少读几条，和「平台压根没发那个请求」
      // 在界面上长得一模一样，而这两件事的下一步完全不同。
      if (notParsed > 0) notes.push(`其中 ${notParsed} 条是重复地址或超出本次上限，没有逐条去读`);
      const note = notes.length ? `（${notes.join("；")}）` : "";
      // **读懂了不等于存下来了。**
      //
      // 这条路把响应体送去 /v1/extension/captures/parse，那个端点只负责「读成条目」，
      // **不落库**——回来的 items 在上面只被数了个数（`items += …length`），条目本身丢掉了。
      // 而报给用户的原话是「共 12 条收藏。」：他按了一下、看到自己的收藏被认出来了，
      // 合理的理解就是「进去了」。**然后资料库里一条都没有。**
      //
      // 这正是 INV-NO-SILENT-ZERO 要防的形状，只不过这次出现在一句话里而不是一个计数里。
      // 让它真的入库是 T10（那还要一条非诊断的安装路，见 evidence/T09），**这里先把话说准**：
      // 说清这一按是探路、东西还没进去、下一步是什么。
      const importedNote = items > 0
        ? `**这 ${items} 条还没有进你的档案馆**——这一按是探路，`
          + `目的是找出该盯哪个地址。找到之后才谈把它们收进来。`
        : "";
      return {
        ok: readable > 0, readable, total: netCaptureBuffer.length, items, dropped,
        parsed: toParse.length, notParsed, readableUrls,
        // **这一按到底有没有把东西存下来**，让调用方能直接读，不用去解那句中文。
        imported: 0,
        failureCode: readable > 0 ? null : (firstProblem?.failure_code || "UNREADABLE"),
        message_zh: readable > 0
          ? `拦到 ${netCaptureBuffer.length} 条${note}，其中 ${readable} 条读得懂，共 ${items} 条收藏。`
            + importedNote
          : (firstProblem?.message_zh || "拦到了响应，但一条都读不懂。") + note,
      };
    }
    if (message?.type === "SA_GET_NET_CAPTURES") {
      // 只回形态与条数，不回响应体——响应体里可能有平台返回的个人信息，
      // 让它在消息里到处传是没必要的暴露面。
      return { ok: true, count: netCaptureBuffer.length,
               urls: netCaptureBuffer.map(item => item.url),
               totalBytes: netCaptureBuffer.reduce((sum, item) => sum + item.body.length, 0) };
    }
    // 删除：SA_CONNECT_PLATFORM_SESSION。它和 connectPlatformSessionByCookies()
    // 是逐行重复的两份同一逻辑，而界面走的是函数直调（connectPlatform 分流）。
    // 两份同样的东西只有一份会被改到，另一份就成了下一次「看着接上了」的来源。
    //
    // 西方三源的会话导出（v0.0.0.7 / T06）。cookies 是**可选权限**：
    // 装插件时不申请，只在用户点「连接 X」这一刻才要。用户拒绝授权时说清楚
    // 是没授权，不要退回"没登录"——那两件事的下一步不一样。
    // 断开账号（v0.0.0.7 / INV-REVERSIBLE）。走 background 而不是让设置页直接
    // 调接口：服务端标成 disconnected 之后，**扩展本地队列里那条待办还在**，
    // 下一次唤醒照样会去跑它——服务端说断开了、插件还在同步，是最难查的那种不一致。
    if (message?.type === "SA_DISCONNECT_ACCOUNT") {
      const accountId = String(message.accountId || "").trim();
      if (!accountId) return { ok: false, error: "没有指定要断开的账号。" };
      const result = await SA.api(`/v1/accounts/${encodeURIComponent(accountId)}`, {
        method: "DELETE", timeoutMs: 15000,
      });
      const removed = await removeQueuedSync({ accountId });
      return { ok: true, state: "disconnected", removedFromQueue: removed,
               message_zh: result?.message_zh || "已断开连接。" };
    }
    if (message?.type === "SA_REVOKE_PLATFORM_SESSION") {
      const platform = String(message.platform || "").trim().toLowerCase();
      const config = await SA.getConfig();
      const response = await fetch(`${config.endpoint}/v1/credentials/${encodeURIComponent(platform)}`, {
        method: "DELETE", headers: { Authorization: `Bearer ${config.token}` },
      }).catch(() => null);
      if (!response?.ok) return { ok: false, error: "撤销失败，请稍后重试。" };
      // 顺手把浏览器这边的权限也还回去——库里删了但权限还留着，
      // 用户看到的仍是"这个插件能读我的 Cookie"。
      const spec = globalThis.SACookieExport?.ALLOWED_PLATFORMS?.[platform];
      if (spec) {
        await chrome.permissions.remove({
          origins: spec.domains.flatMap(d => [`https://*.${d}/*`, `https://${d}/*`]),
        }).catch(() => null);
      }
      return { ok: true, state: "disconnected", message_zh: "已撤销，服务器上的登录信息已删除。" };
    }
    if (message?.type === "SA_OPEN_OPTIONS") {
      await chrome.runtime.openOptionsPage();
      return { ok: true };
    }
    return { ok: false, error: "未知操作" };
  })().then(sendResponse).catch(error => sendResponse({ ok: false, state: "needs_user_action", error: error?.message || "操作失败" }));
  return true;
});
