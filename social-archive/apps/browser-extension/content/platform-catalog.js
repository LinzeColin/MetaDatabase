/**
 * 平台目录 —— 「这个平台叫什么、支持哪几种关系、收藏页在哪个 URL」。
 *
 * ## 它为什么单独存在
 *
 * v0.0.0.6 里这张表混在 `content/account-mirror-core.js` 的 `PLATFORM_SPECS` 中，
 * 和 DOM 选择器（`contentPatterns` / `collectionText` / `relationTabMatchers`）挤在
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
        // 抓取时代这里要靠选中态判定；拦截时代由响应体自带关系字段，
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

  const api = Object.freeze({ PLATFORMS, platformCatalogEntry, platformLabel, relationUrl });
  globalThis.SAPlatformCatalog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
