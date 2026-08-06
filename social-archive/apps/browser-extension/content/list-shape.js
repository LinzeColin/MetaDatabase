/** 从「这个页面发出的所有响应」里认出哪个是收藏列表（v0.0.0.21）。
 *
 * ## 为什么要这个
 *
 * 小红书 / 抖音 / 快手的主路径是「扩展读取页面和列表」，做法是在 Owner
 * 自己已登录的收藏页上**拦截平台自己发出的那个列表请求**——不是我们去调，
 * 所以不需要破解签名（页面自己会签）。
 *
 * 挡住这条路的一直是「要先知道那个请求的 URL 前缀」。
 * `INTERCEPT_PREFIXES` 里三个平台都是 null，而它们的正当来源是
 * **Owner 去收藏页按一次诊断按钮，把前缀抓回来固化**。
 * 他的原话：「不要让我和你重复地反攻」——那一步不该由他做。
 *
 * 而观察器本来就支持不带前缀（net-observer.js:97
 * `urlPrefixes.length === 0 || shouldCapture(url)`）：**全都收下**。
 * 于是问题从「先知道地址」变成「收下之后认出哪个是列表」——
 * 后者不需要他做任何事。
 *
 * ## 按形状认，不按地址认
 *
 * 一个收藏列表响应长什么样，跨平台是稳定的：
 *
 *   · 某处有一个**数组**
 *   · 数组里的元素是对象，且**多数元素带同一批字段**
 *   · 那些字段里有能唯一标识一条内容的东西（id / note_id / aweme_id / photoId）
 *   · 通常还带标题或描述、作者、时间
 *
 * 而不是列表的响应（配置、埋点、用户信息、推荐流）要么没有数组，
 * 要么数组太短、要么元素结构不齐。
 *
 * ## 三条不许违反的规矩
 *
 * 1. **认不出就说认不出**，不许返回空数组当成「他没有收藏」
 *    （INV-NO-SILENT-ZERO）。
 * 2. **把候选和落选都报出来**：每个响应为什么被选中/淘汰，要说得出。
 *    一个只说「找到了」的识别器，出错时没人查得动。
 * 3. **不猜平台**。这个文件里没有任何平台名——它只认形状。
 *    某个平台改了接口，这里不用改；某个平台加进来，这里也不用改。
 */
(() => {
  "use strict";

  // 一条内容至少要有的：一个能当外部 id 的字段
  const ID_KEYS = ["note_id", "aweme_id", "photo_id", "photoId", "bvid", "id",
                   "item_id", "video_id", "content_id", "rid"];
  const TITLE_KEYS = ["title", "desc", "description", "caption", "display_title",
                      "content", "text", "name"];
  const AUTHOR_KEYS = ["author", "user", "nickname", "owner", "upper", "user_name"];
  const TIME_KEYS = ["create_time", "created_at", "time", "timestamp", "publish_time",
                     "fav_time", "collect_time"];

  // 一个数组至少要这么多元素才当它是列表。
  // 太小的话，一条配置里的两个开关也会被当成列表。
  const MIN_ITEMS = 3;
  // 至少这么大比例的元素要长得一样，才算「同一批东西」。
  const MIN_HOMOGENEITY = 0.7;

  function has(object, keys) {
    if (!object || typeof object !== "object") return null;
    for (const key of keys) {
      const value = object[key];
      if (value !== undefined && value !== null && value !== "") return key;
    }
    return null;
  }

  /** 把 JSON 里所有「像列表」的数组找出来，连同它在哪。 */
  function findArrays(payload, path, out, depth) {
    if (depth > 8 || out.length > 200) return out;
    if (Array.isArray(payload)) {
      if (payload.length >= MIN_ITEMS
          && payload.every(item => item && typeof item === "object" && !Array.isArray(item))) {
        out.push({ path, items: payload });
      }
      // 数组里可能还套着数组
      payload.slice(0, 20).forEach((item, index) =>
        findArrays(item, `${path}[${index}]`, out, depth + 1));
      return out;
    }
    if (payload && typeof payload === "object") {
      for (const [key, value] of Object.entries(payload)) {
        findArrays(value, path ? `${path}.${key}` : key, out, depth + 1);
      }
    }
    return out;
  }

  /** 给一个数组打分：它有多像一批收藏条目。 */
  function score(items) {
    const sample = items.slice(0, 50);
    let withId = 0, withTitle = 0, withAuthor = 0, withTime = 0;
    const idKeys = new Set();
    for (const item of sample) {
      const idKey = has(item, ID_KEYS);
      if (idKey) { withId += 1; idKeys.add(idKey); }
      if (has(item, TITLE_KEYS)) withTitle += 1;
      if (has(item, AUTHOR_KEYS)) withAuthor += 1;
      if (has(item, TIME_KEYS)) withTime += 1;
    }
    const n = sample.length || 1;
    const idRate = withId / n;
    // **齐不齐**比「有没有」更能分辨列表与杂物：
    // 一批收藏条目字段高度一致，而推荐流／配置往往参差不齐。
    const homogeneous = idRate >= MIN_HOMOGENEITY;
    return {
      count: items.length,
      id_rate: Number(idRate.toFixed(2)),
      title_rate: Number((withTitle / n).toFixed(2)),
      author_rate: Number((withAuthor / n).toFixed(2)),
      time_rate: Number((withTime / n).toFixed(2)),
      id_keys: [...idKeys],
      // 打分：**id 是硬条件**，其余是加分项
      points: homogeneous
        ? idRate * 4 + (withTitle / n) * 2 + (withAuthor / n) + (withTime / n)
        : 0,
      rejected: homogeneous ? "" : `只有 ${Math.round(idRate * 100)}% 的元素带得出 id，不像一批同类条目`,
    };
  }

  /** 从一批抓到的响应里挑出最像收藏列表的那一个。
   *
   * @param captures [{url, status, text}]
   * @returns {ok, best?, candidates, rejected, failureCode?, error?}
   */
  /** 诊断里只留路径，**丢掉查询串**。
   *
   * 平台的列表接口常把签名/时间戳/token 放在查询串里
   * （抖音的 a_bogus、小红书的 xsec_token 都是）。诊断会跟着同步回执
   * 落到服务端，而这个仓的硬规矩是**凭据绝不落进日志或证据**。
   * 只留路径不影响用处：我要的是"哪个端点"，不是那串签名。
   */
  function safePath(url) {
    const text = String(url || "");
    try {
      const parsed = new URL(text);
      return parsed.origin + parsed.pathname;
    } catch (_) {
      return text.split("?")[0].slice(0, 300);
    }
  }

  function recogniseList(captures) {
    const candidates = [];
    const rejected = [];
    for (const capture of captures || []) {
      const url = String(capture?.url || "");
      let payload;
      try {
        payload = JSON.parse(String(capture?.text || ""));
      } catch (_) {
        rejected.push({ url: safePath(url), why: "不是 JSON" });
        continue;
      }
      const arrays = findArrays(payload, "", [], 0);
      if (!arrays.length) {
        rejected.push({ url: safePath(url), why: `没有长度 ≥ ${MIN_ITEMS} 的对象数组` });
        continue;
      }
      let bestHere = null;
      for (const found of arrays) {
        const stats = score(found.items);
        if (stats.points <= 0) continue;
        if (!bestHere || stats.points > bestHere.stats.points) {
          bestHere = { url, path: found.path, items: found.items, stats };
        }
      }
      if (bestHere) candidates.push(bestHere);
      else {
        const why = score(arrays[0].items).rejected || "数组里的元素不像内容条目";
        rejected.push({ url: safePath(url), why });
      }
    }
    candidates.sort((a, b) => b.stats.points - a.stats.points);
    if (!candidates.length) {
      // **认不出就说认不出。** 绝不返回空列表当成「他没有收藏」。
      return {
        ok: false,
        failureCode: "LIST_SHAPE_NOT_RECOGNISED",
        error: "在这个页面发出的响应里没有认出收藏列表。"
               + "请确认你正停在收藏夹页面上、并且已经往下滚动过。",
        candidates: [], rejected,
      };
    }
    return { ok: true, best: candidates[0], candidates, rejected };
  }

  /** 把认出来的条目归一化。**不认识的字段一律不猜**，宁可少几个字段。 */
  function normaliseItems(best, { platform, urlBuilder } = {}) {
    const items = [];
    const skipped = [];
    for (const raw of best.items) {
      const idKey = has(raw, ID_KEYS);
      const externalId = idKey ? String(raw[idKey]) : "";
      const url = typeof urlBuilder === "function"
        ? urlBuilder(raw, externalId)
        : (has(raw, ["url", "link", "share_url", "note_url"])
            ? String(raw[has(raw, ["url", "link", "share_url", "note_url"])]) : "");
      if (!/^https?:\/\//i.test(String(url || ""))) {
        skipped.push({ id: externalId, reason: "没有能在浏览器里打开的网址" });
        continue;
      }
      const titleKey = has(raw, TITLE_KEYS);
      const authorKey = has(raw, AUTHOR_KEYS);
      const authorRaw = authorKey ? raw[authorKey] : null;
      items.push({
        url,
        external_content_id: externalId.slice(0, 512) || null,
        title: titleKey ? String(raw[titleKey]).slice(0, 2048) : null,
        author_name: (typeof authorRaw === "string" ? authorRaw
          : authorRaw && typeof authorRaw === "object"
            ? String(authorRaw.nickname || authorRaw.name || authorRaw.user_name || "")
            : "").slice(0, 1024) || null,
        // **这里也要剥。** raw_metadata 会入库、会出现在导出里，
        // 而签名/token 就在查询串上。同一个泄漏点的第二处——
        // 这个仓在「修一处就当修完了」上栽过四次，这次一起修。
        raw_metadata: { source: "page_response_shape", platform: platform || "",
                        matched_path: best.path, matched_url: safePath(best.url) },
      });
    }
    return { items, skipped };
  }

  const api = Object.freeze({
    recogniseList, normaliseItems, findArrays, score, safePath,
    MIN_ITEMS, MIN_HOMOGENEITY, ID_KEYS,
  });
  globalThis.SAListShape = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
