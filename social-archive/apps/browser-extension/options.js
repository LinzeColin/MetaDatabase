/* global SA */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const platformOrder = ["generic-web", "xiaohongshu", "douyin", "kuaishou", "bilibili", "x", "reddit", "instagram"];
  const platformNames = { "generic-web":"Chrome 书签", xiaohongshu:"小红书", douyin:"抖音", kuaishou:"快手", bilibili:"B站", x:"X", reddit:"Reddit", instagram:"Instagram" };
  const platformIcons = { "generic-web":"书", xiaohongshu:"红", douyin:"抖", kuaishou:"快", bilibili:"B", x:"X", reddit:"R", instagram:"I" };
  const relationCopy = {
    "generic-web":"全部 Chrome 书签与文件夹", xiaohongshu:"收藏夹、收藏、点赞", douyin:"收藏夹、收藏、点赞",
    kuaishou:"收藏、点赞", bilibili:"收藏夹、稍后再看、历史、点赞", x:"书签、点赞", reddit:"Saved、Upvoted", instagram:"Saved Collections"
  };
  const destinationNames = { social_archive:"主档案", markdown:"Markdown", notion:"Notion", obsidian:"Obsidian", github:"GitHub Private", karakeep:"Karakeep", linkwarden:"Linkwarden", archivebox:"ArchiveBox" };
  const activeStates = new Set(["queued","authorizing","discovering","scanning","normalizing","artifacting","exporting"]);
  let config = null;
  let accounts = [];
  let runs = [];
  let destinations = [];
  let pendingConnections = {};
  // 托管中的登录状态（v0.0.0.7 / T06）。服务端 GET /v1/credentials 只回形态：
  // 平台、有没有、几条、什么时候存的。**永远不回 cookie 的名或值。**
  let credentials = [];
  // 每个平台「现在同步得动吗」，来自服务端（account_sync.SYNCABLE_NOW）。
  // **网页那侧修过一遍，这一侧漏了** —— 同一份假话在两个界面各有一份。
  let platformSupport = {};
  let serviceReady = false;

  function setServiceMessage(message = "", type = "needs") {
    const node = $("serviceMessage");
    node.textContent = message;
    node.className = `message ${type}`.trim();
    node.classList.toggle("hidden", !message);
  }

  function toast(message, type="success") {
    const node = $("toast");
    node.textContent = message;
    node.className = `toast ${type === "success" ? "" : type}`.trim();
    node.classList.remove("hidden");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => node.classList.add("hidden"), 4200);
  }
  function stateLabel(value) { return ({connected:"已连接",degraded:"降级可用",disconnected:"未连接",authorizing:"正在授权",queued:"等待同步",discovering:"正在发现",scanning:"正在同步",normalizing:"正在整理",artifacting:"正在归档",exporting:"正在导出",completed:"同步完成",partial:"部分完成",failed:"需要处理",blocked_environment:"重新连接"})[value] || value || "未连接"; }
  function latestRun(accountId) { return runs.filter(run => run.source_account_id === accountId).sort((a,b)=>String(b.updated_at||"").localeCompare(String(a.updated_at||"")))[0] || null; }
  function formatTime(value) { if(!value)return"尚未同步";const d=new Date(value);return Number.isNaN(d.getTime())?"尚未同步":new Intl.DateTimeFormat("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(d).replaceAll("/","-"); }

  async function checkService() {
    config = await SA.getConfig();
    $("endpoint").value = config.endpoint;
    // v0.0.0.7 / T03：判据只剩一条——**拿现有凭据真的调一次受保护接口**。
    // 旧实现先问服务端「还要不要配对」，再据此决定要不要弹出手抄码的输入框。
    // 那条链路已删；而且它把"服务说不用配对"当成"我连得上"，中间隔着凭据有没有效。
    try {
      await SA.api("/v1/extension/bootstrap", {timeoutMs:6000});
      serviceReady = true;
      $("serviceState").className = "state connected";
      $("serviceState").textContent = "已连接";
      $("serviceBadge").className = "badge connected";
      $("serviceBadge").textContent = "私人档案馆已连接";
      setServiceMessage();
      return true;
    } catch (_) {
      serviceReady = false;
      $("serviceState").className = "state error";
      $("serviceState").textContent = "待连接";
      $("serviceBadge").className = "badge error";
      $("serviceBadge").textContent = "需要连接";
      // 没连上时不再要用户输入任何东西——指路去已登录的档案馆页面点一下即可。
      setServiceMessage("还没有连上私人档案馆。请打开档案馆页面并登录，插件会自动接上，无需输入任何内容。", "needs");
      return false;
    }
  }

  async function loadData() {
    if (!await checkService()) { accounts=[]; runs=[]; destinations=[]; credentials=[]; render(); return; }
    try {
      const [accountData, runData, bootstrap, pendingData, credentialData] = await Promise.all([
        SA.api("/v1/accounts",{timeoutMs:8000}), SA.api("/v1/sync-runs?limit=200",{timeoutMs:8000}), SA.api("/v1/extension/bootstrap",{timeoutMs:8000}),
        chrome.runtime.sendMessage({type:"SA_GET_PENDING_CONNECTIONS"}).catch(()=>({items:{}})),
        // 单独兜底：托管状态读不到不该让整页空白——其余四项是这一页的主体。
        SA.api("/v1/credentials",{timeoutMs:8000}).catch(()=>({items:[]}))
      ]);
      accounts=accountData.items||[]; runs=runData.items||[]; destinations=bootstrap.destinations||[]; pendingConnections=pendingData.items||{};
      platformSupport=Object.fromEntries((accountData.supported_platforms||[]).map(item=>[item.platform,item]));
      credentials=credentialData.items||[];
    } catch(error){ toast(`状态读取失败：${error.message}`,"error"); }
    render();
  }

  function renderSummary() {
    const connected=accounts.filter(a=>["connected","degraded"].includes(a.connection_state));
    const total=connected.reduce((sum,a)=>sum+Number(a.content_count||0),0);
    const active=runs.filter(run=>activeStates.has(run.status));
    $("connectedCount").textContent=String(connected.length);
    $("contentCount").textContent=total.toLocaleString("zh-CN");
    $("activeCount").textContent=String(active.length);
  }

  function renderAccounts() {
    $("accountGrid").innerHTML=platformOrder.map(platform=>{
      const account=accounts.find(item=>item.platform===platform && (platform!=="generic-web" || item.external_account_id==="chrome-bookmarks"));
      const run=account?latestRun(account.id):null;
      const pending=Boolean(pendingConnections[platform]);
      // 托管登录状态是**独立于 source_account 的**一份事实：走 Cookie 托管连接
      // （connectPlatformSessionByCookies）只会把加密后的登录状态存进服务端，
      // 不会建 source_account 行。此前这一页只看 accounts，于是连接成功弹出
      //「已连接，登录状态已加密保存（N 条）」之后，刷新回来卡片仍显示「未连接」。
      const custody=credentials.find(item=>item.platform===platform && item.connected)||null;
      const status=pending?"authorizing":(run && activeStates.has(run.status)?run.status:(account?.connection_state||(custody?"connected":"disconnected")));
      const imported=Number(run?.imported_count||0),discovered=Number(run?.discovered_count||0);
      const progress=discovered?Math.min(100,Math.round(imported/discovered*100)):(run&&activeStates.has(run.status)?18:(account?100:0));
      // 失败时优先显示**为什么**（v0.0.0.7 / T14）。message_zh 由服务端算好下发，
      // 词典只有一处真源，扩展不再需要自己抄一份——先前它压根没有词典，
      // 同步失败只显示状态标签「需要处理」，说不出原因。
      const failureText = run && run.last_error_code ? (run.message_zh || "") : "";
      const meta=pending
        ? `登录页已经打开。完成登录后会自动继续；未自动识别时点击“我已登录”。`
        : failureText
          ? failureText
          : account
            ? (run&&activeStates.has(run.status)?`已导入 ${imported.toLocaleString("zh-CN")}/${discovered?discovered.toLocaleString("zh-CN"):"…"} 条`:`${Number(account.content_count||0).toLocaleString("zh-CN")} 条 · ${formatTime(account.last_sync_at)}`)
            : custody
              ? `登录状态已加密保存（${Number(custody.cookie_count||0).toLocaleString("zh-CN")} 条）· ${formatTime(custody.updated_at)}`
              : (platformSupport[platform]?.sync_supported === false
                ? (platformSupport[platform]?.not_syncable_reason || "本版本还不能自动同步这个平台。")
                : relationCopy[platform]);
      // 「随时可以一键撤销」是连接成功时**当着用户面许下的原话**（background.js）。
      // 此前撤销只存在于两处代码里：服务端 DELETE /v1/credentials/{platform}，
      // 以及扩展的 SA_REVOKE_PLATFORM_SESSION 处理体——**而没有任何界面发出这条消息**。
      // 也就是说这句承诺在产品上是假的。这颗按钮就是把它变成真的。
      const revoke=custody?`<button class="card-button danger" data-revoke-platform="${platform}">撤销登录状态</button>`:"";
      // **同步不了的平台不给同步/连接按钮。**
      //
      // 与网页那侧同一条规则（见 account_sync.SYNCABLE_NOW）。小红书/抖音/
      // 快手/B站 的取数路在本版本是 stub：画了按钮点下去必然失败，
      // 而失败文案曾经说的是「暂时连不上服务器，[ 重试 ]」。
      const syncable = platformSupport[platform]?.sync_supported !== false;
      // **「同步不了」不等于「连了没用」。** 网页那侧犯过一次同样的错：
      // 把 x / instagram 移出「能同步」之后，这段逻辑顺手把它们的**连接入口**
      // 也一起关了。那对国内四家是对的（Cookie 一步不离开浏览器，服务端根本
      // 不接收），对 x / instagram 是错的（托管的登录状态会被取原文件那条路用到）。
      // 服务端为此单独下发 connect_supported，依据是 credentials.CUSTODIAL_PLATFORMS。
      const connectable = platformSupport[platform]?.connect_supported !== false;
      // **守卫必须排在最前面。** 放在 pending 之后的话，一个同步不了的平台
      // 只要还留着未完成的连接流程，就仍会画出「我已登录，继续」和「重新打开」
      // ——把人推进一条走到头也没用的路。这一处是新加的那道门抓出来的，
      // 不是我自己看出来的。
      const action=!syncable
        ? (account
            ? `<button class="card-button danger" data-disconnect-account="${SA.escapeHtml(account.id)}">断开连接</button>${revoke}`
            : connectable
              ? `<button class="card-button" data-connect-platform="${platform}">连接账号</button>`
              : "")
        : pending
        ? `<button class="card-button primary" data-verify-platform="${platform}">我已登录，继续</button><button class="card-button" data-connect-platform="${platform}">重新打开</button>`
        : account
          ? `<button class="card-button primary" data-sync-account="${SA.escapeHtml(account.id)}">立即同步</button>${["blocked_environment","failed"].includes(status)?`<button class="card-button" data-connect-platform="${platform}">重新连接</button>`:""}<button class="card-button danger" data-disconnect-account="${SA.escapeHtml(account.id)}">断开连接</button>${revoke}`
          : custody
            ? `<button class="card-button" data-connect-platform="${platform}">重新连接</button>${revoke}`
            : `<button class="card-button primary" data-connect-platform="${platform}">连接账号</button>`;
      return `<article class="account-card"><header><span class="platform-icon">${platformIcons[platform]}</span><span class="account-title"><strong>${platformNames[platform]}</strong><small>${SA.escapeHtml(account?.display_name||"未连接")}</small></span><span class="state ${SA.escapeHtml(status)}">${SA.escapeHtml(stateLabel(status))}</span></header><div class="account-meta">${SA.escapeHtml(meta)}</div><div class="progress"><span style="width:${progress}%"></span></div><div class="account-actions">${action}</div></article>`;
    }).join("");
    document.querySelectorAll("[data-connect-platform]").forEach(button=>button.addEventListener("click",()=>connectPlatform(button.dataset.connectPlatform,button)));
    document.querySelectorAll("[data-verify-platform]").forEach(button=>button.addEventListener("click",()=>verifyPlatform(button.dataset.verifyPlatform,button)));
    document.querySelectorAll("[data-sync-account]").forEach(button=>button.addEventListener("click",()=>syncAccount(button.dataset.syncAccount,button)));
    document.querySelectorAll("[data-revoke-platform]").forEach(button=>button.addEventListener("click",()=>revokePlatform(button.dataset.revokePlatform,button)));
    document.querySelectorAll("[data-disconnect-account]").forEach(button=>button.addEventListener("click",()=>disconnectAccount(button.dataset.disconnectAccount,button)));
  }

  function renderDestinations() {
    const order=["social_archive","markdown","notion","obsidian","github","karakeep","archivebox","linkwarden"];
    const map=new Map(destinations.map(item=>[item.destination_id,item]));
    $("destinationGrid").innerHTML=order.map(id=>{
      const item=map.get(id)||{};const state=id==="social_archive"||id==="markdown"?(item.state||"connected"):(item.state||"needs_user_action");
      return `<article class="destination-card"><header><strong>${destinationNames[id]}</strong><span class="state ${SA.escapeHtml(state)}">${SA.escapeHtml(SA.statusCopy(state))}</span></header><p>${SA.escapeHtml(item.last_message_zh||item.next_action_zh||(state==="connected"?"自动写入已开启":"在网站连接向导中完成一次真实写入"))}</p><p class="muted">${SA.escapeHtml(item.coverage_zh||"")}</p></article>`;
    }).join("");
  }
  function render(){renderSummary();renderAccounts();renderDestinations();}

  async function connectPlatform(platform,button){
    if(!serviceReady){toast("请先连接私人档案馆","needs");location.hash="service";return;}
    button.disabled=true;button.textContent="正在连接…";
    try{
      const result=await chrome.runtime.sendMessage({type:"SA_ACCOUNT_CONNECT",platform});
      if(!result?.ok)throw new Error(result?.error||"连接未完成");
      toast(result.message||"授权流程已打开");
      if(result.state==="connected")await loadData();
      else setTimeout(()=>loadData().catch(()=>{}),2500);
    }catch(error){toast(`${platformNames[platform]}：${error.message}`,"error");}
    finally{button.disabled=false;button.textContent="连接账号";}
  }
  async function verifyPlatform(platform,button){
    button.disabled=true;button.textContent="正在检查…";
    try{const result=await chrome.runtime.sendMessage({type:"SA_VERIFY_PLATFORM_SESSION",platform});if(!result?.ok)throw new Error(result?.error||"尚未检测到登录状态");toast(result.message||"账号已连接，首次同步已经开始");await loadData();}
    catch(error){toast(`${platformNames[platform]}：${error.message}`,"needs");}
    finally{button.disabled=false;button.textContent="我已登录，继续";}
  }
  /** 一键撤销托管的登录状态（v0.0.0.7 / T06 · INV-REVERSIBLE）。
   *
   * 走 background 而不是直接 fetch：撤销要做的**不止**服务端删库那一半，
   * 还要把浏览器这边的 cookies 权限一起还回去（chrome.permissions.remove）。
   * 只删服务端的话，用户在扩展详情页看到的仍然是「这个插件能读我的 Cookie」——
   * 撤销了却看不出撤销了，和没撤销一样。那段逻辑在 background 里，
   * 权限 API 也只有 background 能调。
   */
  async function revokePlatform(platform,button){
    if(!confirm(`撤销后，服务器上保存的 ${platformNames[platform]||platform} 登录状态会被立即删除，插件也会交还读取该站点 Cookie 的权限。\n\n需要时可以重新连接。确定撤销吗？`))return;
    button.disabled=true;button.textContent="正在撤销…";
    try{
      const result=await chrome.runtime.sendMessage({type:"SA_REVOKE_PLATFORM_SESSION",platform});
      if(!result?.ok)throw new Error(result?.error||"撤销失败");
      toast(result.message_zh||"已撤销，服务器上的登录信息已删除。");
      await loadData();
    }catch(error){toast(`${platformNames[platform]||platform}：${error.message}`,"error");}
    finally{button.disabled=false;button.textContent="撤销登录状态";}
  }
  /** 断开账号（v0.0.0.7 / INV-REVERSIBLE）。
   *
   * 连接是一次点击，此前**断开做不到**——而连上之后每 6 小时自己跑一次，
   * 用户没有任何办法让它停下来。这颗按钮就是那个「停」。
   *
   * 措辞刻意把「不再同步」和「内容留着」分开说：断开是"别再替我去取了"，
   * 不是"把我存的东西清掉"。归档的意义就是东西留下来。
   */
  async function disconnectAccount(accountId,button){
    const account=accounts.find(item=>item.id===accountId);
    const name=account?platformNames[account.platform]||account.platform:"这个账号";
    const kept=Number(account?.content_count||0).toLocaleString("zh-CN");
    if(!confirm(`断开 ${name} 之后不会再自动同步。\n\n已经存下的 ${kept} 条内容都会留着，随时可以重新连接。\n\n确定断开吗？`))return;
    button.disabled=true;button.textContent="正在断开…";
    try{
      const result=await chrome.runtime.sendMessage({type:"SA_DISCONNECT_ACCOUNT",accountId});
      if(!result?.ok)throw new Error(result?.error||"断开失败");
      toast(result.message_zh||"已断开连接。");
      await loadData();
    }catch(error){toast(`${name}：${error.message}`,"error");}
    finally{button.disabled=false;button.textContent="断开连接";}
  }
  async function syncAccount(accountId,button){
    button.disabled=true;button.textContent="正在启动…";
    try{const result=await chrome.runtime.sendMessage({type:"SA_SYNC_ACCOUNT",accountId});if(!result?.ok)throw new Error(result?.error||"同步失败");toast("同步已开始，已完成内容会立即出现在资料库");await loadData();}
    catch(error){toast(`同步失败：${error.message}`,"error");}
    finally{button.disabled=false;button.textContent="立即同步";}
  }
  async function syncAll(){
    $("syncAll").disabled=true;
    try{const result=await chrome.runtime.sendMessage({type:"SA_SYNC_ALL_ACCOUNTS"});if(!result?.ok)throw new Error("请先连接账号");toast("已启动全部账号同步");await loadData();}
    catch(error){toast(error.message,"needs");}
    finally{$("syncAll").disabled=false;}
  }
  /** 打开档案馆页面去连接（v0.0.0.7 / T03）。
   *
   * 这里**不再有任何输入框**。凭据由已登录的档案馆页面替扩展取好并直接递过来，
   * 用户在这个页面一个字符都不用输入——这是 T03 的 Acceptance 原文要求。
   */
  async function openLibraryToConnect(){
    $("connectService").disabled=true;
    try{
      const libraryUrl=String(config.libraryUrl||"").replace(/\/$/,"");
      if(!/^https?:\/\//i.test(libraryUrl))throw new Error("档案馆地址无效，请检查服务连接设置。");
      await chrome.tabs.create({url:libraryUrl,active:true});
      toast("已打开档案馆页面，登录后插件会自动接上。");
    }catch(error){toast(error.message,"error");}
    finally{$("connectService").disabled=false;}
  }

  $("connectService").addEventListener("click",openLibraryToConnect);
  $("syncAll").addEventListener("click",syncAll);
  $("jumpAccounts").addEventListener("click",()=>{location.hash="accounts";$("accounts").scrollIntoView({behavior:"smooth"});});
  $("refreshAccounts").addEventListener("click",loadData);
  $("openLibrary").addEventListener("click",async()=>chrome.tabs.create({url:(await SA.getConfig()).libraryUrl}));
  $("openDestinationCenter").addEventListener("click",async()=>chrome.tabs.create({url:`${(await SA.getConfig()).libraryUrl}/?open=destinations`}));
  $("finish").addEventListener("click",async()=>{await SA.setConfig({onboardingComplete:true});chrome.tabs.create({url:(await SA.getConfig()).libraryUrl});});
  loadData();
})();
