/**
 * 平台目录 —— 「这个平台叫什么、支持哪几种关系、收藏页在哪个 URL」。
 *
 * ## 它为什么单独存在
 *
 * v0.0.0.6 里这张表混在「账号镜像核心」那个文件的平台规格对象中，
 * 和三类 DOM 选择器（内容路径正则、收藏夹文案正则、关系标签匹配器）挤在
 * 同一个对象里。T03 要删的是 DOM 抓取，照字面把那个文件整体删掉，会把这四个字段
 * 一起删掉——而它们**和抓取方式无关**：
 *
 *   · `label`        界面文案要显示「B站账号」
 *   · `relations`    发起同步时要知道该平台有哪几种关系（background.js:690 据此循环）
 *   · `home`         无论用什么方式取数，都得先把标签页导到平台首页
 *   · `relationUrls` 「B站收藏夹在哪个 URL」——换成 API 拦截之后**更需要**它，
 *                    因为拦截的前提是先让浏览器真的去访问那个页面
 *
 * T08 的 MAIN-world 拦截路会继续用这四个字段。放在这里，是为了让「删抓取器」
 * 这件事不会顺手把它们带走，也不必让 T08 再造一遍。
 *
 * ## 边界
 *
 * 这个文件里**不许**出现 DOM 选择器、文本正则、标签页选中态判定。
 * 那些属于抓取实现，已随 v0.0.0.7 删除，且有守卫测试盯着它们别回来
 * （`tests/focused/test_superseded_paths_stay_removed.py`）。
 */
(() => {
  "use strict";

  const PLATFORMS = Object.freeze({
    xiaohongshu: Object.freeze({
      label: "小红书",
      relations: ["favorite", "like"],
      home: "https://www.xiaohongshu.com/explore",
      relationUrls: Object.freeze({
        // 收藏与点赞共用个人主页路由，靠页面内的标签切换区分。
        // 旧实现要靠标签选中态去判；换成拦截之后由响应体自带关系字段，
        // 所以两条关系指向同一个 URL 是正确的，不是遗漏。
        favorite: "https://www.xiaohongshu.com/user/profile",
        like: "https://www.xiaohongshu.com/user/profile"
      })
    }),
    douyin: Object.freeze({
      label: "抖音",
      relations: ["favorite", "like"],
      home: "https://www.douyin.com/",
      relationUrls: Object.freeze({
        favorite: "https://www.douyin.com/user/self?showTab=collection",
        like: "https://www.douyin.com/user/self?showTab=like"
      })
    }),
    kuaishou: Object.freeze({
      label: "快手",
      relations: ["favorite", "like"],
      home: "https://www.kuaishou.com/",
      relationUrls: Object.freeze({
        // 同小红书：共用主页路由。
        favorite: "https://www.kuaishou.com/profile",
        like: "https://www.kuaishou.com/profile"
      })
    }),
    bilibili: Object.freeze({
      label: "B站",
      relations: ["favorite", "watch_later", "history", "like"],
      home: "https://www.bilibili.com/",
      relationUrls: Object.freeze({
        favorite: "https://space.bilibili.com/0/favlist",
        watch_later: "https://www.bilibili.com/watchlater/list",
        history: "https://www.bilibili.com/account/history",
        like: "https://space.bilibili.com/0"
      })
    }),
    youtube: Object.freeze({
      label: "YouTube",
      relations: ["watch_later", "playlist"],
      home: "https://www.youtube.com/",
      relationUrls: Object.freeze({
        watch_later: "https://www.youtube.com/playlist?list=WL",
        playlist: "https://www.youtube.com/feed/playlists"
      })
    }),
    x: Object.freeze({
      label: "X",
      relations: ["bookmark", "like"],
      home: "https://x.com/home",
      relationUrls: Object.freeze({
        bookmark: "https://x.com/i/bookmarks",
        like: "https://x.com/home"
      })
    }),
    reddit: Object.freeze({
      label: "Reddit",
      relations: ["saved", "upvoted"],
      home: "https://www.reddit.com/",
      relationUrls: Object.freeze({
        saved: "https://www.reddit.com/user/me/saved/",
        upvoted: "https://www.reddit.com/user/me/upvoted/"
      })
    }),
    instagram: Object.freeze({
      label: "Instagram",
      relations: ["saved"],
      home: "https://www.instagram.com/",
      relationUrls: Object.freeze({
        saved: "https://www.instagram.com/your_activity/saved/"
      })
    })
  });

  /** 拦截用的 URL 前缀（v0.0.0.7 / T08）。
   *
   * ⚠️ **这张表只许写实测抓到过的前缀，不许凭印象写。**
   *
   * 预制件 net-observer.js 的原话：「这些前缀必须来自真实抓包，不要凭印象写。
   * 首次运行时把命中的完整 URL 记进 evidence，供 Build Agent 校正。」
   *
   * 猜错前缀的后果正是 INV-NO-SILENT-ZERO 要防的形状：观察器装上了、
   * 页面正常、一条都没拦到、界面显示"已连接"——和"这个人真的没有收藏"
   * 长得一模一样。所以没实测过的一律写 null，而不是写一个看着像的。
   *
   * bilibili 这条有三处独立来源互相印证：
   *   · 01_PRODUCT/FEATURE_MATRIX.md 第 33 行
   *   · 00_CONTROL/PROJECT_CAPSULE.yaml 的 api.bilibili.com/x/v3/fav/*
   *   · 14_EVIDENCE/PREPARATION_RECORD.json 的核对记录（引 bilibili-API-collect）
   * 且该接口是纯 REST 无签名，是三个国内源里最容易先跑通的一个。
   *
   * 小红书与抖音写 null：任务包没有给出实测过的收藏列表接口前缀，
   * T09「抓到即固化」才是取得它们的正当途径。
   */
  const INTERCEPT_PREFIXES = Object.freeze({
    bilibili: Object.freeze(["api.bilibili.com/x/v3/fav/resource/list"]),
    xiaohongshu: null,
    douyin: null,
  });

  /** 一次同步**真的去枚举**的关系类型（v0.0.0.7 / G1）。
   *
   * 与上面 `PLATFORMS[x].relations`（**允许**出现的关系）不是一回事——
   * 服务端 `_scannable_relations()` 早就把这两件事分开了（它把 `manual_save`
   * 排除在扫描范围外：手动存的那些没有任何页面能列出来）。这里是同一条道理
   * 在扩展这一侧的对应物。
   *
   * 为什么必须有它：B 站声明了四种关系（收藏夹/稍后再看/历史/点赞），
   * 而 G1 只把**收藏夹**那条取数路做出来了。照 `spec.relations` 循环的话，
   * 一次同步会跑四轮、后三轮各抛一次 ACQUISITION_PATH_NOT_INSTALLED，
   * 于是「收藏夹明明读成功了」的那次运行整体停在非完成态，
   * 用户看到的是一个失败的同步——**而他要的那件事其实成了**。
   *
   * 规则和 SYNCABLE_NOW 一样：**这是事实清单，不是愿景清单。**
   * 取数路没做出来的关系不许写进来；写进来就等于承诺这一版读得到。
   */
  const SCANNABLE_RELATIONS = Object.freeze({
    // 收藏夹走 B 站自己的公开接口（content/bilibili-reader.js），2026-08-06 实测。
    // 稍后再看 / 历史 / 点赞三条的取数路本版本没有做，所以不列。
    bilibili: Object.freeze(["favorite"]),
    // v0.0.0.21：这三个走「按形状认页面自己发的列表」。
    // 只读收藏——点赞那条列表页面不一定会发，没验过就不承诺。
    xiaohongshu: Object.freeze(["favorite"]),
    douyin: Object.freeze(["favorite"]),
    kuaishou: Object.freeze(["favorite"]),
    // v0.0.0.22：同一条路。Reddit 的 saved、Instagram 的 saved 都有
    // **不需要用户名的固定地址**（/user/me/saved、/your_activity/saved），
    // 所以能直接导过去。upvoted 那条没验过，不列——不列就等于不承诺。
    reddit: Object.freeze(["saved"]),
    instagram: Object.freeze(["saved"]),
  });

  /** 取数是**调平台自己的接口**，而不是读页面（v0.0.0.8）。
   *
   * 这个区别决定了同步要不要动用户的标签页：
   *
   *   读页面  →  必须把标签页导航到那个关系页、等它加载完
   *   调接口  →  只需要一个**该平台源**的标签页（为了带上登录态、过 CORS），
   *              停在哪一页都行，也不必在前台
   *
   * 2026-08-06 实测（端到端演练）：同步会新开一个标签页、把它导航到
   * `space.bilibili.com/0/favlist` 并**切到前台**。自动同步每 6 小时一次——
   * 等于每 6 小时抢一次他的屏幕，而他什么都没点。
   * 取数改成调接口之后，那次导航连必要性都没有了。
   */
  const API_ACQUISITION = Object.freeze({ bilibili: true });

  function acquiresViaPlatformApi(platform) {
    return API_ACQUISITION[String(platform || "")] === true;
  }

  /** 关系类型的中文名（v0.0.0.13）。
   *
   * 放在这里而不是各页面自己写一份，是因为这件事已经在三处各说各的：
   * PWA 的 app.js 有一份、options.js 的 relationCopy 有一份**整句的散文**、
   * 服务端 PLATFORM_LABELS 旁边还有一份。散文那份最危险——
   * 它不是逐项列举，而是一句写死的话，改了扫描范围也不会有人想起去改它。
   */
  const RELATION_LABELS = Object.freeze({
    manual_save: "手动保存", bookmark: "书签", saved: "已保存", favorite: "收藏夹",
    like: "点赞", upvoted: "顶过", watch_later: "稍后再看", history: "观看历史",
    playlist: "播放列表", collection: "收藏夹",
  });

  function relationLabel(relation) {
    const key = String(relation || "");
    return RELATION_LABELS[key] || key;
  }

  /** 这个平台**这一版真的会读**哪些东西，写成一句给人看的话。
   *
   * 设置页那张卡原来用的是一张写死的散文表（options.js 的 relationCopy），
   * B 站那条写着「收藏夹、稍后再看、历史、点赞」——**而这一版只读收藏夹**。
   * 他点「连接账号」时以为四样都会同步，连上之后只会看到一样。
   * 这正是验收标准里那句「绝不给一颗结构上不可能成功的按钮」的同一类问题：
   * 按钮能按，但它承诺的东西有四分之三不会发生。
   */
  function scannableSummary(platform) {
    const relations = scannableRelations(platform);
    if (!relations.length) return "";
    return relations.map(relationLabel).join("、");
  }

  /** 这一版对该平台真的会去枚举哪些关系。
   *
   * 没登记的平台按「声明什么就扫什么」——保持原行为，不悄悄改变别的平台。
   */
  function scannableRelations(platform) {
    const key = String(platform || "");
    if (Object.prototype.hasOwnProperty.call(SCANNABLE_RELATIONS, key)) {
      return Array.from(SCANNABLE_RELATIONS[key]);
    }
    return Array.from(platformCatalogEntry(key)?.relations || []);
  }

  /** 取某平台的拦截前缀。
   *
   * 返回 null 表示**还没有实测过的前缀**——调用方必须把它当成显式失败，
   * 不能当成空数组去装观察器。装上一个前缀为空的观察器 = 永远拦不到，
   * 而且看起来一切正常。
   */
  function interceptPrefixes(platform) {
    const key = String(platform || "");
    return Object.prototype.hasOwnProperty.call(INTERCEPT_PREFIXES, key)
      ? INTERCEPT_PREFIXES[key]
      : null;
  }

  function platformCatalogEntry(platform) {
    return PLATFORMS[String(platform || "")] || null;
  }

  function platformLabel(platform) {
    return platformCatalogEntry(platform)?.label || String(platform || "");
  }

  function relationUrl(platform, relation) {
    const entry = platformCatalogEntry(platform);
    if (!entry) return "";
    return entry.relationUrls?.[relation] || entry.home || "";
  }

  const api = Object.freeze({
    PLATFORMS, platformCatalogEntry, platformLabel, relationUrl,
    INTERCEPT_PREFIXES, interceptPrefixes,
    SCANNABLE_RELATIONS, scannableRelations,
    RELATION_LABELS, relationLabel, scannableSummary,
    API_ACQUISITION, acquiresViaPlatformApi,
  });
  globalThis.SAPlatformCatalog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
