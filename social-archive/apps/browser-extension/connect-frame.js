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
  /** 平台中文名。**不在这里再写一份表。**
   *
   * 这个仓已经有四份平台名表（服务端 PLATFORM_LABELS、扩展目录、
   * 设置页 platformNames、资料库 platformMeta），而我上一版在这里加了第五份——
   * 正是我一直在抱怨的那种漂移：改一个名字要记得改五处，漏一处就有一个界面
   * 显示原始 id。目录（content/platform-catalog.js）已经在这一页里加载了，
   * 它就有 platformLabel。
   *
   * generic-web 目录里没有（它不是平台页面），只这一个特例，写在这儿。
   */
  function label(platform) {
    if (platform === "generic-web" || platform === "chrome-bookmarks") return "Chrome 书签";
    return globalThis.SAPlatformCatalog?.platformLabel?.(platform) || platform;
  }

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

  /** 查一次这个平台的浏览器授权，把结果标在那一行上。
   *
   * 只读：`chrome.permissions.contains` 不弹框、不要手势。
   * 查不动就什么都不改 —— **不许把「我没查到」显示成「没有授权」**。
   */
  async function markPermission(platform, state) {
    const origins = SA.patternsForPlatform(platform) || [];
    if (!origins.length) return;
    let granted;
    try {
      granted = await chrome.permissions.contains({ origins });
    } catch (_) {
      return;
    }
    if (granted) return;
    const base = state.textContent;
    state.textContent = base + " · 缺授权";
    state.classList.add("needs");
    const button = state.parentElement?.querySelector("button");
    if (button) button.textContent = "去授权";
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

    /** 造一颗「连接账号」按钮。**两处共用，不许各写一份。**
     *
     * 2026-08-07 查生产时发现：X / YouTube 的 `connect_supported` 是 true、
     * background 里那条 Cookie 托管的连接路是通的（`connectPlatform` 的注释
     * 写着「别的平台（X / YouTube）连接按钮本来就是 Cookie 托管」）、
     * 服务端下发的原因文案里白纸黑字写着**「点这张卡片上的『连接账号』」**——
     * **而面板对它们一颗按钮都不画。**
     *
     * 他会照着那句话去找，然后找不到。这和「给一颗按不动的按钮」是同一种伤：
     * 说明指向一个不存在的东西。
     */
    function connectButtonFor(platform, name, state, item) {
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
      return button;
    }

    for (const row of rows) {
      const platform = row.platform;
      const item = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = label(platform);
      const state = document.createElement("span");
      state.className = "state";
      state.textContent = connected.has(platform) ? "已连接" : "未连接";
      item.append(name, state, connectButtonFor(platform, name, state, item));
      // **这里也要标。** 上一版只改了下面那个分支（X / YouTube 那条），
      // 于是小红书 / 抖音 / B站——正是他真正在用的三个——一行都没标出来，
      // 而真 Chrome 探针同时证明抖音的授权确实是 false。
      // 「两处建行代码只改了一处」，这个仓当天已经第二次。
      markPermission(platform, state);
      list.append(item);
    }
    for (const row of manualOnly) {
      const item = document.createElement("li");
      item.className = "manual";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = label(row.platform);
      const why = document.createElement("span");
      why.className = "why";
      // 原因由服务端下发（NOT_SYNCABLE_YET），**这里不自己编一句**：
      // 两处各写一份必然漂，这个仓在平台文案上已经漂过好几轮。
      why.textContent = row.not_syncable_reason || "本版本还不能自动读取这个平台。";
      item.append(name, why);
      // **不能自动同步 ≠ 不能连接。**
      //
      // X / YouTube 走的是 Cookie 托管：连上之后登录状态交给他自己的服务器
      // 保管（那是非国内平台，不违反「国内平台 Cookie 不出浏览器」）。
      // 服务端把这件事标在 `connect_supported` 上，文案里也在叫他点这颗按钮。
      // 只按 `sync_supported` 决定画不画，就把一条通着的路做成了够不着的。
      if (row.connect_supported) {
        const state = document.createElement("span");
        state.className = "state";
        state.textContent = connected.has(row.platform) ? "已连接" : "未连接";
        item.append(state, connectButtonFor(row.platform, name, state, item));
        // **「已连接」不等于「读得到」。**（2026-08-18）
        //
        // 2026-08-17 生产实况：抖音那行显示「已连接」，而每一次同步都倒在
        // PLATFORM_PERMISSION_MISSING —— 浏览器那颗「允许读取抖音页面」的
        // 授权根本没给到。两件事在界面上是分开的，**他没有任何办法提前发现**，
        // 只能等一次同步失败之后才看到那句话。
        //
        // 而同步那一刻**没有用户手势**，`chrome.permissions.request` 一定抛，
        // 所以那时也补不回来——只能等他下次再点一次「连接账号」。
        //
        // 这里当场查一次并显示出来：缺授权就把这一行标出来，
        // 顺带把按钮的字改成「去授权」——他要点的还是同一颗，
        // 但知道自己在点什么。
        markPermission(row.platform, state);
      }
      list.append(item);
    }
    // 面板高度告诉外面，免得 iframe 里出现第二根滚动条——**那也是一种乱**。
    tell("size", { height: document.body.scrollHeight });
  }

  render().catch(error => say(`打不开：${error.message}`, "error"));
})();
