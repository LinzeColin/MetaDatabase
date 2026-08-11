/** B 站收藏夹读取器 —— 在 Owner 自己的浏览器里，用 B 站自己的公开接口（v0.0.0.7 / G1）。
 *
 * ## 为什么是这条路
 *
 * `acquireRelationItems()` 这个缝口从 T03 删掉 DOM 抓取器之后一直是显式 stub，
 * 于是 `SYNCABLE_NOW` 里只剩 `generic-web`（Chrome 书签）。Owner 2026-08-06 的原话：
 * 「我希望最后我来验收能给到我的是一个操作简单、满足要求、多平台聚合到一起的一个软件。」
 * 只有书签能自动读，那句话就没兑现。
 *
 * 原计划是 T08「在浏览器里拦平台自己的 API 响应」，但那条路要 Owner 先去收藏夹页
 * 按一次诊断，把前缀抓出来——**而这正是他说的「不要让我和你重复地反攻」。**
 *
 * 这里改成主动调：B 站的收藏夹接口是公开 REST，不需要签名、不需要 API key。
 * 请求从**他自己的 B 站页面**里发出去，浏览器自动带上他自己的登录态：
 *
 *   · **零费用** —— 没有 API key，没有付费档，不碰 L0 那条硬边界。
 *   · **Cookie 不出浏览器（INV-DOMESTIC-COOKIE-STAYS）** —— 我们从不读、不存、
 *     不传 cookie 的名或值；带凭据的是浏览器自己，和他打开那个页面时一模一样。
 *   · **不用他按任何诊断按钮** —— 接口地址在下面写死，来源是实测（见「实测记录」）。
 *
 * 比拦截更强的一点：**翻页终点是接口自己说的**（`data.has_more`），
 * 而不是「滚到没动静了就当作到底了」。到底没到底不用猜。
 *
 * ## 实测记录（2026-08-06，直接打真实接口量的，不是读文档推的）
 *
 *   GET /x/web-interface/nav                      未登录 → {"code":-101,"message":"账号未登录"}
 *   GET /x/v3/fav/folder/created/list-all?up_mid= 看不见 → {"code":0,"message":"OK","data":null}
 *   GET /x/v3/fav/resource/list?media_id=…        有数据 → data.medias[] / data.has_more / data.info.media_count
 *   CORS：Origin: https://space.bilibili.com 时回
 *         access-control-allow-credentials: true + allow-origin 回显该源
 *         → 从他的 B 站页面里带登录态读，是被允许的。
 *
 * **两个用测量换来的判断，写在这儿免得以后有人"顺手简化"掉：**
 *
 * 1. **`code === 0` 不等于读到了。** 看不见的收藏夹回的是
 *    `{"code":0,"message":"OK","data":null}` —— 成功码、成功文案、空数据。
 *    照着 `data?.list || []` 写就会得到「同步成功，0 条」，
 *    也就是 INV-NO-SILENT-ZERO 明令禁止、v0.0.0.6 生产上真的发生过的那种零。
 *    所以下面 `classify()` 把 `data == null` 单独判成失败。
 *
 * 2. **`media.link` 不能当网址用。** 它的真实值是 `bilibili://video/116980698843032`
 *    —— 一个 App 深链，在浏览器里打不开。网址必须由 `bvid` 拼：
 *    `https://www.bilibili.com/video/{bvid}`。
 *    直接用 link 的话，入库的每一条都是点不开的。
 *
 * ## 它不做什么
 *
 * · 不读、不存、不传 cookie。
 * · 不写任何东西回 B 站（只有 GET）。
 * · 不碰别的平台。小红书 / 抖音 / 快手的收藏接口没有实测过，
 *   **没量过的一律不写**——那是 INTERCEPT_PREFIXES 里三个 null 的同一条规矩。
 */
(() => {
  "use strict";

  const API = "https://api.bilibili.com";
  const PAGE_SIZE = 20;
  // 单个收藏夹的翻页上限。存在的理由是防翻页逻辑写错时打死循环，
  // **不是**"只同步前 4000 条"——真撞上了会报 partial + 明确原因，不会假装读完了。
  const MAX_PAGES = 200;

  /** 一次响应到底算不算"读到了"。
   *
   * 这个函数是这份文件里最要紧的十几行：`code === 0` 有三种完全不同的含义，
   * 分不开就会把「看不见」报成「空的」。
   */
  function classify(payload) {
    if (!payload || typeof payload !== "object") {
      return { ok: false, failureCode: "BILIBILI_SHAPE_UNKNOWN",
               error: "B 站接口回的不是一个能读的对象。" };
    }
    const code = Number(payload.code);
    if (code === -101 || code === -400 && /未登录/.test(String(payload.message || ""))) {
      return { ok: false, failureCode: "BILIBILI_NOT_LOGGED_IN",
               error: "你在这个浏览器里还没登录 B 站，或者登录已经过期。请先在 B 站页面登录，再同步一次。" };
    }
    if (code === -403) {
      return { ok: false, failureCode: "BILIBILI_FORBIDDEN",
               error: "B 站拒绝了这次读取（没有权限）。" };
    }
    if (code !== 0) {
      return { ok: false, failureCode: "BILIBILI_API_ERROR",
               error: `B 站接口回了错误码 ${code}：${String(payload.message || "").slice(0, 120)}` };
    }
    // **成功码 + 空数据。** 实测就是这个形状，见文件头第 1 条。
    if (payload.data === null || payload.data === undefined) {
      return { ok: false, failureCode: "BILIBILI_FOLDER_NOT_VISIBLE",
               error: "B 站说这次请求成功，但没有给任何数据——通常是这个收藏夹不可见，或者登录态没带上。"
                      + "**这不是「你没有收藏」**，所以不会记成同步成功。" };
    }
    return { ok: true, data: payload.data };
  }

  /** 条目的网址。**只认 http(s)**，`bilibili://` 深链一律拒绝。 */
  function webUrlFor(media) {
    const bvid = String(media?.bvid || media?.bv_id || "").trim();
    if (/^BV[0-9A-Za-z]{8,}$/.test(bvid)) return `https://www.bilibili.com/video/${bvid}`;
    for (const candidate of [media?.link, media?.media_list_link]) {
      const text = String(candidate || "").trim();
      if (/^https?:\/\//i.test(text)) return text;
    }
    return "";
  }

  function isoFromUnix(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return null;
    return new Date(value * 1000).toISOString();
  }

  /** 一条 media → CaptureRequest 的形状。
   *
   * **只许出现 CaptureRequest 有的字段**：服务端那个模型是 `extra="forbid"`，
   * 多一个键整批 422，而批次是 200 条一发——一个拼错的键能让 200 条全数落空。
   * platform / relation_type / collection_key / destination_ids 由
   * sendBrowserScopeBatches 统一补，这里不要写。
   */
  function normalise(media, collectionKey = "") {
    const url = webUrlFor(media);
    if (!url) return null;
    const cover = String(media?.cover || "");
    return {
      url,
      external_content_id: String(media?.id ?? "").slice(0, 512) || null,
      collection_key: String(collectionKey || "").slice(0, 512),
      title: String(media?.title || "").slice(0, 2048) || null,
      author_name: String(media?.upper?.name || "").slice(0, 1024) || null,
      text: String(media?.intro || "").slice(0, 200000) || null,
      published_at: isoFromUnix(media?.pubtime),
      relation_observed_at: isoFromUnix(media?.fav_time),
      media_urls: /^https?:\/\//i.test(cover) ? [cover] : [],
      raw_metadata: {
        source: "bilibili_fav_api",
        bvid: String(media?.bvid || media?.bv_id || ""),
        avid: media?.id ?? null,
        media_type: media?.type ?? null,
        duration: media?.duration ?? null,
        page_count: media?.page ?? null,
      },
    };
  }

  async function call(path, fetchImpl) {
    const doFetch = fetchImpl || globalThis.fetch;
    let response;
    try {
      // **credentials: "include" 是整条路的关键，也是唯一碰到登录态的地方。**
      // 带凭据的是浏览器自己；这段代码从不读 cookie 的名或值。
      response = await doFetch(`${API}${path}`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
    } catch (error) {
      return { ok: false, failureCode: "BILIBILI_NETWORK_ERROR",
               error: `连不上 B 站接口：${String(error?.message || error).slice(0, 160)}` };
    }
    if (!response.ok) {
      return { ok: false, failureCode: "BILIBILI_HTTP_ERROR",
               error: `B 站接口回了 HTTP ${response.status}。` };
    }
    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      return { ok: false, failureCode: "BILIBILI_SHAPE_UNKNOWN",
               error: "B 站接口回的不是 JSON。" };
    }
    return classify(payload);
  }

  /** 当前登录的是谁。拿不到 mid 就没法列收藏夹，所以这一步失败必须显式往上报。 */
  async function currentUser(fetchImpl) {
    const result = await call("/x/web-interface/nav", fetchImpl);
    if (!result.ok) return result;
    const mid = Number(result.data?.mid);
    if (!result.data?.isLogin || !Number.isFinite(mid) || mid <= 0) {
      return { ok: false, failureCode: "BILIBILI_NOT_LOGGED_IN",
               error: "你在这个浏览器里还没登录 B 站。请先登录，再同步一次。" };
    }
    return { ok: true, mid, name: String(result.data?.uname || "") };
  }

  /** 他建的收藏夹清单。**这是权威来源**——v0.0.0.6 是从页面文案里正则猜的。 */
  async function listFolders(mid, fetchImpl) {
    const result = await call(`/x/v3/fav/folder/created/list-all?up_mid=${encodeURIComponent(mid)}`, fetchImpl);
    if (!result.ok) return result;
    const raw = Array.isArray(result.data?.list) ? result.data.list : [];
    const folders = raw
      .map(item => ({
        mediaId: String(item?.id ?? ""),
        title: String(item?.title || "未命名收藏夹").slice(0, 256),
        mediaCount: Number(item?.media_count ?? 0),
      }))
      .filter(item => item.mediaId);
    // 收藏夹一个都没有，是**真的可能**发生的（新号），而且它和"读失败"分得开：
    // 上面 classify 已经把 data==null 挡掉了，能走到这里说明 data 是个真对象。
    return { ok: true, folders, declaredCount: Number(result.data?.count ?? raw.length) };
  }

  /** 读一个收藏夹的全部条目。
   *
   * 完整性由**接口自己**说了算（`has_more`），再和 `info.media_count` 对一次账。
   * 对不上不报 complete —— 少读了却说读完了，后面的"消失检测"会把没读到的
   * 当成"他取消收藏了"，那是会丢数据的。
   */
  async function readFolder(mediaId, { fetchImpl = null, pageSize = PAGE_SIZE } = {}) {
    const items = [];
    const skipped = [];
    let expected = null;
    let folderTitle = "";
    let page = 1;
    let sawHasMore = false;

    for (; page <= MAX_PAGES; page += 1) {
      const result = await call(
        `/x/v3/fav/resource/list?media_id=${encodeURIComponent(mediaId)}`
        + `&pn=${page}&ps=${pageSize}&platform=web&order=mtime`, fetchImpl);
      if (!result.ok) {
        // 已经读到一部分再失败：**报 partial 并带上已读到的**，不要整份丢掉。
        return { ok: items.length > 0, items, skipped, partial: true,
                 failureCode: result.failureCode, error: result.error,
                 expected, folderTitle, pagesRead: page - 1 };
      }
      const data = result.data;
      if (expected === null) expected = Number(data?.info?.media_count ?? NaN);
      if (!folderTitle) folderTitle = String(data?.info?.title || "");
      const medias = Array.isArray(data?.medias) ? data.medias : [];
      for (const media of medias) {
        const normalised = normalise(media, mediaId);
        if (normalised) items.push(normalised);
        // **读不出网址的要报出来，不能默默丢。** 默默丢 = 静默的少读。
        else skipped.push({ id: media?.id ?? null, title: String(media?.title || "").slice(0, 80),
                            reason: "这一条没有能在浏览器里打开的网址（bvid 与 link 都不可用）" });
      }
      sawHasMore = Boolean(data?.has_more);
      // 接口说没有更多了 → 到底了。这是权威终点，不是"滚不动了"。
      if (!sawHasMore) break;
      // 说还有更多、这一页却是空的 → 不能再翻，否则死循环。
      if (medias.length === 0) {
        return { ok: items.length > 0, items, skipped, partial: true,
                 failureCode: "BILIBILI_PAGINATION_STUCK",
                 error: "B 站说还有更多，但这一页一条都没给——停在这里，不假装读完了。",
                 expected, folderTitle, pagesRead: page };
      }
    }

    if (sawHasMore) {
      return { ok: true, items, skipped, partial: true,
               failureCode: "BILIBILI_TOO_MANY_PAGES",
               error: `这个收藏夹超过 ${MAX_PAGES * pageSize} 条，本次只读了前面一部分。`,
               expected, folderTitle, pagesRead: MAX_PAGES };
    }
    // 对账：接口自己声明的条数 vs 真的拿到手的条数（含读不出网址被跳过的）。
    const accounted = items.length + skipped.length;
    const countMatches = !Number.isFinite(expected) || accounted === expected;
    return {
      ok: true, items, skipped,
      partial: !countMatches,
      failureCode: countMatches ? null : "BILIBILI_COUNT_MISMATCH",
      error: countMatches ? null
        : `这个收藏夹声明有 ${expected} 条，实际只读到 ${accounted} 条——差额没有解释，所以不算读完。`,
      expected, folderTitle, pagesRead: page,
    };
  }

  /** 一次读完他所有的收藏夹。返回值直接喂给 acquireRelationItems 的调用方。 */
  async function readAllFavorites({ fetchImpl = null, pageSize = PAGE_SIZE } = {}) {
    const who = await currentUser(fetchImpl);
    if (!who.ok) return { ok: false, failureCode: who.failureCode, error: who.error };

    const listed = await listFolders(who.mid, fetchImpl);
    if (!listed.ok) return { ok: false, failureCode: listed.failureCode, error: listed.error };

    const items = [];
    const skipped = [];
    const collections = [];
    const problems = [];
    for (const folder of listed.folders) {
      const read = await readFolder(folder.mediaId, { fetchImpl, pageSize });
      items.push(...(read.items || []));
      skipped.push(...(read.skipped || []));
      collections.push({
        collection_key: folder.mediaId,
        collection_name: read.folderTitle || folder.title,
        declared: Number.isFinite(read.expected) ? read.expected : folder.mediaCount,
        read: (read.items || []).length,
        complete: Boolean(read.ok) && !read.partial,
        reason: read.error || null,
      });
      if (read.partial || !read.ok) {
        problems.push(`「${folder.title}」：${read.error || "没读完"}`);
      }
    }

    const allComplete = collections.length > 0 && collections.every(c => c.complete);
    // **收藏夹一个都没有**：这是真的可能的，但绝不能报成 complete + 0 条，
    // 那和"读失败"在界面上长得一模一样。给它一个自己的失败码。
    if (listed.folders.length === 0) {
      return { ok: false, failureCode: "BILIBILI_NO_FOLDERS",
               error: "在你的 B 站账号下没有找到任何收藏夹。如果你确实有收藏夹，"
                      + "多半是登录态没带上——请在 B 站页面确认你是登录状态。" };
    }
    return {
      ok: true,
      items,
      completeness: allComplete && skipped.length === 0 ? "complete" : "partial",
      failureCode: allComplete && skipped.length === 0 ? null
        : (skipped.length ? "BILIBILI_SOME_ITEMS_HAVE_NO_URL" : "BILIBILI_SOME_FOLDERS_INCOMPLETE"),
      completionReason: problems.length ? problems.slice(0, 5).join("；")
        : (skipped.length ? `有 ${skipped.length} 条读不出可打开的网址，已跳过并记下。` : null),
      cursor: {
        source: "bilibili_fav_api",
        account_mid: who.mid,
        collections_found: collections.length,
        observed_count: items.length,
        skipped_count: skipped.length,
        collections,
      },
    };
  }

  const api = Object.freeze({
    classify, webUrlFor, normalise, isoFromUnix,
    currentUser, listFolders, readFolder, readAllFavorites,
    PAGE_SIZE, MAX_PAGES,
  });
  globalThis.SABilibiliReader = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
