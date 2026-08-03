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
    if (!await checkService()) { accounts=[]; runs=[]; destinations=[]; render(); return; }
    try {
      const [accountData, runData, bootstrap, pendingData] = await Promise.all([
        SA.api("/v1/accounts",{timeoutMs:8000}), SA.api("/v1/sync-runs?limit=200",{timeoutMs:8000}), SA.api("/v1/extension/bootstrap",{timeoutMs:8000}),
        chrome.runtime.sendMessage({type:"SA_GET_PENDING_CONNECTIONS"}).catch(()=>({items:{}}))
      ]);
      accounts=accountData.items||[]; runs=runData.items||[]; destinations=bootstrap.destinations||[]; pendingConnections=pendingData.items||{};
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
      const status=pending?"authorizing":(run && activeStates.has(run.status)?run.status:(account?.connection_state||"disconnected"));
      const imported=Number(run?.imported_count||0),discovered=Number(run?.discovered_count||0);
      const progress=discovered?Math.min(100,Math.round(imported/discovered*100)):(run&&activeStates.has(run.status)?18:(account?100:0));
      const meta=pending
        ? `登录页已经打开。完成登录后会自动继续；未自动识别时点击“我已登录”。`
        : account
          ? (run&&activeStates.has(run.status)?`已导入 ${imported.toLocaleString("zh-CN")}/${discovered?discovered.toLocaleString("zh-CN"):"…"} 条`:`${Number(account.content_count||0).toLocaleString("zh-CN")} 条 · ${formatTime(account.last_sync_at)}`)
          : relationCopy[platform];
      const action=pending
        ? `<button class="card-button primary" data-verify-platform="${platform}">我已登录，继续</button><button class="card-button" data-connect-platform="${platform}">重新打开</button>`
        : account
          ? `<button class="card-button primary" data-sync-account="${SA.escapeHtml(account.id)}">立即同步</button>${["blocked_environment","failed"].includes(status)?`<button class="card-button" data-connect-platform="${platform}">重新连接</button>`:""}`
          : `<button class="card-button primary" data-connect-platform="${platform}">连接账号</button>`;
      return `<article class="account-card"><header><span class="platform-icon">${platformIcons[platform]}</span><span class="account-title"><strong>${platformNames[platform]}</strong><small>${SA.escapeHtml(account?.display_name||"未连接")}</small></span><span class="state ${SA.escapeHtml(status)}">${SA.escapeHtml(stateLabel(status))}</span></header><div class="account-meta">${SA.escapeHtml(meta)}</div><div class="progress"><span style="width:${progress}%"></span></div><div class="account-actions">${action}</div></article>`;
    }).join("");
    document.querySelectorAll("[data-connect-platform]").forEach(button=>button.addEventListener("click",()=>connectPlatform(button.dataset.connectPlatform,button)));
    document.querySelectorAll("[data-verify-platform]").forEach(button=>button.addEventListener("click",()=>verifyPlatform(button.dataset.verifyPlatform,button)));
    document.querySelectorAll("[data-sync-account]").forEach(button=>button.addEventListener("click",()=>syncAccount(button.dataset.syncAccount,button)));
  }

  function renderDestinations() {
    const order=["social_archive","markdown","notion","obsidian","github","karakeep","archivebox","linkwarden"];
    const map=new Map(destinations.map(item=>[item.destination_id,item]));
    $("destinationGrid").innerHTML=order.map(id=>{
      const item=map.get(id)||{};const state=id==="social_archive"||id==="markdown"?(item.state||"connected"):(item.state||"needs_user_action");
      return `<article class="destination-card"><header><strong>${destinationNames[id]}</strong><span class="state ${SA.escapeHtml(state)}">${SA.escapeHtml(SA.statusCopy(state))}</span></header><p>${SA.escapeHtml(item.last_message_zh||item.next_action_zh||(state==="connected"?"自动写入已开启":"在网站连接向导中完成一次真实写入"))}</p></article>`;
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
