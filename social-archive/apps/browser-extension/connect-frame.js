/* global SA */
/** 嵌在资料库里的「连接账号」小面板（v0.0.0.22）。
 *
 * 它存在的唯一理由是**不跳页**：`chrome.permissions.request` 只能在扩展
 * 自己的页面里、在一次用户手势期间调用，所以这一页必须是扩展页面；
 * 而它以 iframe 嵌在资料库里，所以他人没离开原来那一页。
 *
 * **这里不重写连接逻辑**。它只做两件 background 做不到的事：
 *   1. 在手势还在的时候把权限要到手
 *   2. 把结果告诉外面那一页
 * 真正的连接仍然是 background 的 SA_ACCOUNT_CONNECT。
 * 两份同样的逻辑只有一份会被改到——这个仓为此删过一个消息处理器。
 */
(() => {
  "use strict";

  const list = document.getElementById("list");
  const note = document.getElementById("note");
  const LABELS = {
    "generic-web": "Chrome 书签", xiaohongshu: "小红书", douyin: "抖音",
    kuaishou: "快手", bilibili: "B站", x: "X", reddit: "Reddit",
    instagram: "Instagram", youtube: "YouTube",
  };

  /** 把诊断摆成一段能整段复制的话。 */
  function showDiagnosis(detail) {
    const box = document.getElementById("diagnosis");
    if (!box) return;
    if (!detail) { box.hidden = true; box.textContent = ""; return; }
    const lines = [`抓到 ${detail.captured ?? "?"} 条响应，没有一条像收藏列表。`];
    for (const item of (detail.rejected || []).slice(0, 6)) {
      lines.push(`· ${item.url} —— ${item.why}`);
    }
    box.textContent = `把下面这段整段发给我，我照着修：\n${lines.join("\n")}`;
    box.hidden = false;
  }

  /** 「我已登录，继续」——就地长出来的第二颗按钮。 */
  function showVerify(platform, label, item, state) {
    if (item.querySelector("[data-verify]")) return;
    const verify = document.createElement("button");
    verify.type = "button";
    verify.dataset.verify = platform;
    verify.textContent = "我已登录，继续";
    verify.addEventListener("click", async () => {
      verify.disabled = true;
      verify.textContent = "正在检查…";
      try {
        const result = await chrome.runtime.sendMessage({
          type: "SA_VERIFY_PLATFORM_SESSION", platform });
        if (!result?.ok) {
          const failure = new Error(result?.error || "还没检测到登录状态");
          failure.diagnosis = result?.diagnosis || null;
          throw failure;
        }
        say(result.message || `${label}已连接。`);
        showDiagnosis(null);
        state.textContent = "已连接";
        verify.remove();
        tell("connected", { platform, state: "connected" });
      } catch (error) {
        say(`${label}：${error.message}`, "error");
        showDiagnosis(error.diagnosis);
      } finally {
        verify.disabled = false;
        verify.textContent = "我已登录，继续";
      }
    });
    item.append(verify);
  }

  function say(message, kind = "") {
    note.textContent = message || "";
    note.className = `note ${kind}`.trim();
  }

  /** 告诉外面那一页：这里发生了什么。 */
  function tell(type, detail) {
    parent.postMessage({ source: "social-archive-connect-frame", type, ...detail }, "*");
  }

  /** 这颗按钮那条路会用到哪些权限——**在手势还在的时候一次要齐**。
   *
   * 和 options.js 的 grantWhatConnectNeeds 是同一条规矩，**名字也保持一致**：
   * 判据按这个名字认「发连接消息前有没有先在页面里要权限」。这里必须重复一次
   * 而不是调那边：两份文件不共享作用域，而**把它挪进 shared.js 会让
   * background 也能调到一个只在页面里才成立的函数**——那正是这个 bug 的来源。
   */
  async function grantWhatConnectNeeds(platform, custodial, mediaSession) {
    const origins = SA.patternsForPlatform(platform) || [];
    const permissions = [];
    if (platform === "generic-web" || platform === "chrome-bookmarks") permissions.push("bookmarks");
    else if (custodial.includes(platform) && !mediaSession.includes(platform)) permissions.push("cookies");
    const request = {};
    if (permissions.length) request.permissions = permissions;
    if (origins.length) request.origins = origins;
    if (!request.permissions && !request.origins) return true;
    if (await chrome.permissions.contains(request).catch(() => false)) return true;
    return chrome.permissions.request(request).catch(() => false);
  }

  async function render() {
    let accounts = { items: [], supported_platforms: [] };
    try {
      accounts = await SA.api("/v1/accounts", { timeoutMs: 8000 });
    } catch (error) {
      say(`读不到可连接的来源：${error.message}`, "error");
      return;
    }
    let custodial = [];
    let mediaSession = [];
    try {
      const reply = await chrome.runtime.sendMessage({ type: "SA_MEDIA_SESSION_PLATFORMS" });
      custodial = Array.isArray(reply?.custodial) ? reply.custodial : [];
      mediaSession = Array.isArray(reply?.platforms) ? reply.platforms : [];
    } catch (_) { /* 读不到就按"不需要额外权限"处理，下一步会自己报错 */ }

    const connected = new Set((accounts.items || [])
      .filter(item => ["connected", "degraded"].includes(item.connection_state))
      .map(item => item.platform));
    // **连不上的不画按钮，但要把话说清。**
    //
    // 上一版是直接不显示。那不叫说清：他打开面板找 X，一行都没有，
    // 于是不知道是这个软件不支持、还是自己没找对地方。
    // Owner 的验收标准第 1 条写的是「做不到自动的平台，界面必须**当场说清**
    // 这个只能手动保存」——**不显示不等于说清**。
    //
    // 所以照列，只是不画按钮，把服务端那句原因显示在旁边。
    // 一颗结构上不可能成功的按钮比没有按钮更伤人；而一行没有解释的空白
    // 同样让人卡住。
    const all = accounts.supported_platforms || [];
    const rows = all.filter(item => item.sync_supported !== false);
    const manualOnly = all.filter(item => item.sync_supported === false);
    if (!rows.length) {
      list.innerHTML = "<li><span class=\"name\">本版本还没有能自动同步的来源。</span></li>";
      return;
    }
    list.innerHTML = "";
    for (const row of rows) {
      const platform = row.platform;
      const item = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = LABELS[platform] || platform;
      const state = document.createElement("span");
      state.className = "state";
      state.textContent = connected.has(platform) ? "已连接" : "未连接";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = connected.has(platform) ? "重新连接" : "连接账号";
      button.addEventListener("click", async () => {
        button.disabled = true;
        const original = button.textContent;
        button.textContent = "正在连接…";
        say("");
        try {
          if (!await grantWhatConnectNeeds(platform, custodial, mediaSession)) {
            say(`${name.textContent}：还没有获得需要的授权。再点一次，并在浏览器弹出的框里选「允许」。`, "error");
            return;
          }
          const result = await chrome.runtime.sendMessage({ type: "SA_ACCOUNT_CONNECT", platform });
          if (!result?.ok) {
            // **诊断要挂在 error 上，不然下面那句 showDiagnosis 永远是空的。**
            // 我第一版就漏了这一步——"建好了没接上"当场又犯一次，
            // 而它只有在真 Chrome 里跑一遍才看得见。
            const failure = new Error(result?.error || "连接未完成");
            failure.diagnosis = result?.diagnosis || null;
            throw failure;
          }
          say(result.message || `${name.textContent}已连接。`);
          showDiagnosis(null);
          if (result.state === "connected") {
            state.textContent = "已连接";
            button.textContent = "重新连接";
          } else {
            // **自动认不出登录态时，下一步必须就在这一页上。**
            //
            // 连接会先在后台轮询确认；确认不了（多半是他还没在那个平台登录）
            // 就把平台页翻到前台，让他先登录。此前这颗「我已登录，继续」
            // 只在插件的账号页上有——**面板上没有**，于是他登录完回到面板，
            // 手里只有一颗「连接账号」，而再点一次就是从头再来。
            // 我在给他的说明里把这一步写成了一条路，而那条路当时是断的。
            state.textContent = "等你登录";
            showVerify(platform, name.textContent, item, state);
          }
          tell("connected", { platform, state: result.state || "" });
        } catch (error) {
          say(`${name.textContent}：${error.message}`, "error");
          // **认不出的时候，把「为什么」也摆出来。**
          //
          // 那段诊断（抓到几条响应、每条为什么被淘汰）插件早就算好并放在
          // 返回值的 diagnosis 里，而**服务端和界面没有任何地方读它**——
          // 于是他只看到「没认出你的收藏列表」，而我要的东西谁也拿不到，
          // 只能再来一轮：「你把界面上那句话抄给我」。他说过不要这种来回。
          //
          // 这里就地渲染成一段可以整段复制的话。**不含签名和查询串**：
          // 诊断里的地址早在 list-shape.js 的 safePath 就剥过了。
          showDiagnosis(error.diagnosis);
        } finally {
          button.disabled = false;
          button.textContent = original;
        }
      });
      item.append(name, state, button);
      list.append(item);
    }
    for (const row of manualOnly) {
      const item = document.createElement("li");
      item.className = "manual";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = LABELS[row.platform] || row.platform;
      const why = document.createElement("span");
      why.className = "why";
      // 原因由服务端下发（NOT_SYNCABLE_YET），**这里不自己编一句**：
      // 两处各写一份必然漂，这个仓在平台文案上已经漂过好几轮。
      why.textContent = row.not_syncable_reason || "本版本还不能自动读取这个平台。";
      item.append(name, why);
      list.append(item);
    }
    // 面板高度告诉外面，免得 iframe 里出现第二根滚动条——**那也是一种乱**。
    tell("size", { height: document.body.scrollHeight });
  }

  render().catch(error => say(`打不开：${error.message}`, "error"));
})();
