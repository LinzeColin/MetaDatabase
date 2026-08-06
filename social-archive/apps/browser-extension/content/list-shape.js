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

  // 能拿来拼网址的「链接字段」和「短码」。**和 id 分开**：
  // id 是用来认「这是一批同类条目」的，链接是用来打开的，两件事。
  const LINK_KEYS = ["url", "link", "share_url", "note_url", "permalink", "web_url"];
  const SLUG_KEYS = ["shortcode", "code", "bvid"];

  // 一个数组至少要这么多元素才当它是列表。
  // 太小的话，一条配置里的两个开关也会被当成列表。
  const MIN_ITEMS = 3;
  // 至少这么大比例的元素要长得一样，才算「同一批东西」。
  const MIN_HOMOGENEITY = 0.7;
  // 一条元素里往下挖几层去找 id。**不是越深越好**，见下面那段。
  const MAX_ITEM_DEPTH = 5;

  function has(object, keys) {
    if (!object || typeof object !== "object") return null;
    for (const key of keys) {
      const value = object[key];
      if (value !== undefined && value !== null && value !== "") return key;
    }
    return null;
  }

  /** 在一条元素**内部**找字段，广度优先、限深，返回 `{path, value}`。
   *
   * ## 为什么非要这个
   *
   * 第一版只看元素自己身上的字段。用三家真实的响应形状试认，**三家全军覆没**，
   * 理由都一样：「只有 0% 的元素带得出 id」——因为 id 不在元素身上，
   * **在包了一层的对象里**：
   *
   *     Reddit     children[].data.id
   *     Instagram  items[].media.pk
   *     X          entries[].content.itemContent.tweet_results.result.rest_id
   *
   * 「元素外面套一层壳」是极常见的接口写法，第一版碰巧只在**字段摊平**的
   * 响应上验过，就当成通例了。
   *
   * **而且这不只是「多认几个平台」的事**：小红书自己的条目就是
   * `id` 在外、`display_title` / `user.nickname` 在 `note_card` 里。
   * 照第一版的算法，id 找得到（所以照样入库），标题和作者却一个都取不到——
   * **真站上会存进一批没标题没作者的条目**，而判据全绿。
   *
   * ## 挖得越深，越要旁证
   *
   * 往下挖是有代价的：`id` 是最常见的字段名之一，挖五层几乎能在任何数组里
   * 挖出一个 id 来（埋点事件、配置项、实验分组都带 id）。所以加两条约束：
   *
   *   1. **路径要一致**——不是「每条都有 id」，是「每条的 id 在同一个位置」。
   *      杂物数组挖出来的 id 位置七零八落，过不了这条。
   *   2. **挖到壳里去的（路径带 `.`）必须另有标题或作者佐证**，
   *      光有 id 不算。摊平的那种维持原样，不加码。
   */
  function findKeyDeep(root, keys, { scalarOnly = false, maxDepth = MAX_ITEM_DEPTH } = {}) {
    let level = [{ node: root, path: "" }];
    for (let depth = 0; depth <= maxDepth && level.length; depth += 1) {
      const next = [];
      for (const { node, path } of level) {
        if (!node || typeof node !== "object" || Array.isArray(node)) continue;
        for (const key of keys) {
          const value = node[key];
          if (value === undefined || value === null || value === "") continue;
          if (scalarOnly && typeof value === "object") continue;
          return { path: path ? `${path}.${key}` : key, value };
        }
        for (const [key, value] of Object.entries(node)) {
          if (value && typeof value === "object" && !Array.isArray(value)) {
            next.push({ node: value, path: path ? `${path}.${key}` : key });
          }
        }
      }
      // 宽度也要封顶，不然一条巨大的元素能把这里跑成指数
      level = next.length > 60 ? next.slice(0, 60) : next;
    }
    return null;
  }

  function atPath(object, path) {
    if (!path) return object;
    let node = object;
    for (const key of path.split(".")) {
      if (!node || typeof node !== "object") return null;
      node = node[key];
    }
    return node;
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

  /** 给一个数组打分：它有多像一批收藏条目。
   *
   * 关键不是「每条有没有 id」，是「**每条的 id 在不在同一个位置**」——
   * 一批同类条目的结构是一致的，杂物数组不是。所以先统计 id 出现的路径，
   * 取最常见的那一条当基准，其余字段都在**那条路径指向的那层**上找。
   */
  function score(items) {
    const sample = items.slice(0, 50);
    const paths = new Map();
    for (const item of sample) {
      const hit = findKeyDeep(item, ID_KEYS, { scalarOnly: true });
      if (hit) paths.set(hit.path, (paths.get(hit.path) || 0) + 1);
    }
    let idPath = "", withId = 0;
    for (const [path, count] of paths) {
      // 一样多的时候取**浅**的那条：id 比 meta.id 更可能是这批东西的正身
      if (count > withId || (count === withId && path.length < idPath.length)) {
        idPath = path;
        withId = count;
      }
    }
    // id 所在的那层对象，就是这条内容的正身（Reddit 的 `data`、IG 的 `media`）。
    // 标题、作者、时间都要在**它**身上找，不是在外面那层壳上找。
    const corePath = idPath.includes(".") ? idPath.slice(0, idPath.lastIndexOf(".")) : "";
    const idKey = idPath ? idPath.slice(idPath.lastIndexOf(".") + 1) : "";
    let withTitle = 0, withAuthor = 0, withTime = 0;
    for (const item of sample) {
      const core = atPath(item, corePath);
      if (!core || typeof core !== "object") continue;
      if (findKeyDeep(core, TITLE_KEYS, { scalarOnly: true, maxDepth: 2 })) withTitle += 1;
      if (findKeyDeep(core, AUTHOR_KEYS, { maxDepth: 2 })) withAuthor += 1;
      if (findKeyDeep(core, TIME_KEYS, { scalarOnly: true, maxDepth: 2 })) withTime += 1;
    }
    const n = sample.length || 1;
    const idRate = withId / n;
    const titleRate = withTitle / n, authorRate = withAuthor / n, timeRate = withTime / n;
    // **齐不齐**比「有没有」更能分辨列表与杂物：
    // 一批收藏条目字段高度一致，而推荐流／配置往往参差不齐。
    const consistent = idRate >= MIN_HOMOGENEITY;
    // **挖到壳里去的要另有旁证。** 见 findKeyDeep 的那段：`id` 太常见了，
    // 挖五层几乎能在任何数组里挖出一个来。摊平的那种维持原样，不加码。
    const wrapped = Boolean(corePath);
    const corroborated = titleRate >= MIN_HOMOGENEITY || authorRate >= MIN_HOMOGENEITY;
    const homogeneous = consistent && (!wrapped || corroborated);
    return {
      count: items.length,
      id_rate: Number(idRate.toFixed(2)),
      title_rate: Number(titleRate.toFixed(2)),
      author_rate: Number(authorRate.toFixed(2)),
      time_rate: Number(timeRate.toFixed(2)),
      id_keys: idKey ? [idKey] : [],
      id_path: idPath,
      core_path: corePath,
      // 打分：**id 是硬条件**，其余是加分项
      points: homogeneous ? idRate * 4 + titleRate * 2 + authorRate + timeRate : 0,
      rejected: homogeneous ? ""
        : !consistent
          ? `只有 ${Math.round(idRate * 100)}% 的元素在同一个位置带得出 id，不像一批同类条目`
          : `id 藏在 ${corePath} 里（不在元素本身上），而只有 `
            + `${Math.round(titleRate * 100)}% 有标题、${Math.round(authorRate * 100)}% 有作者——`
            + "挖得越深越要旁证，否则埋点和配置里的 id 也会被认成内容",
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
    // **打平时怎么办。**
    //
    // 收藏页上会同时出现收藏列表和推荐流，而它们的形状可以一模一样
    // （都带 id、标题、作者、时间）——纯按形状打分会打平，谁赢是碰运气。
    // 实测：假站上两者都是满分，随机挑中推荐流，于是**6 条首页推荐被当成
    // 他的收藏导进档案馆**。
    //
    // 破平局用**地址里的词**——注意这只是提示，不是前提：
    // 没有这些词照样能认（这条路的全部意义就是不需要预先知道地址），
    // 只有分数打平时才拿它当参考。
    // 反向词同样重要：feed / recommend / explore 这类是推荐流的标志。
    const COLLECTION_HINTS = ["collect", "fav", "bookmark", "star", "like", "history"];
    const FEED_HINTS = ["feed", "recommend", "explore", "discover", "trending", "hot"];
    const hint = (url) => {
      const text = safePath(url).toLowerCase();
      let score = 0;
      if (COLLECTION_HINTS.some(word => text.includes(word))) score += 1;
      if (FEED_HINTS.some(word => text.includes(word))) score -= 1;
      return score;
    };
    candidates.sort((a, b) => {
      const byPoints = b.stats.points - a.stats.points;
      // 分差明显就按分数；只有几乎打平时才看地址提示
      if (Math.abs(byPoints) > 0.01) return byPoints;
      const byHint = hint(b.url) - hint(a.url);
      if (byHint !== 0) return byHint;
      // 还是分不出就取条目多的那个——收藏通常比一屏推荐多
      return b.stats.count - a.stats.count;
    });
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

  /** 把认出来的条目归一化。**不认识的字段一律不猜**，宁可少几个字段。
   *
   * ## 网址是**取**来的，不是**编**来的
   *
   * 优先级写死成这样，而且每条都记下来它是怎么来的（`derived_by`）：
   *
   *   1. 条目自带绝对网址        → 直接用（最可靠）
   *   2. 条目自带相对路径        → 拼上这个平台自己的域（Reddit 的 permalink）
   *   3. 短码 + 模板             → 例如 Instagram 的 `code`
   *   4. id + 模板               → 国内三家走这条，模板在测试里验过
   *   5. **都不成立 → 跳过并报数**，绝不硬拼一个打不开的网址
   *
   * 第 5 条是要害。拼错的网址比没有更糟：它会安安静静地进档案馆，
   * 半年后点开才发现全是 404，而那时已经无从追溯。宁可当场说
   * 「这次 12 条里有 5 条说不出网址」。
   */
  function normaliseItems(best, { platform, urlBuilder, origin } = {}) {
    const items = [];
    const skipped = [];
    const corePath = best.stats?.core_path || "";
    const idKey = (best.stats?.id_keys || [])[0] || "";
    for (const raw of best.items) {
      const core = atPath(raw, corePath);
      if (!core || typeof core !== "object") {
        skipped.push({ id: "", reason: "这条的结构和同批其余的不一样" });
        continue;
      }
      const idValue = idKey && core[idKey] !== undefined && core[idKey] !== null
        ? core[idKey]
        : findKeyDeep(core, ID_KEYS, { scalarOnly: true })?.value;
      const externalId = idValue === undefined || idValue === null ? "" : String(idValue);
      const linkHit = findKeyDeep(core, LINK_KEYS, { scalarOnly: true, maxDepth: 2 });
      const linkText = linkHit ? String(linkHit.value) : "";
      const slugHit = findKeyDeep(core, SLUG_KEYS, { scalarOnly: true, maxDepth: 1 });
      let url = "";
      let derivedBy = "";
      if (/^https?:\/\//i.test(linkText)) {
        url = linkText;
        derivedBy = "link_field";
      } else if (/^\/[^/]/.test(linkText) && origin) {
        url = String(origin).replace(/\/+$/, "") + linkText;
        derivedBy = "relative_link";
      } else if (typeof urlBuilder === "function") {
        const slug = slugHit ? String(slugHit.value) : "";
        url = urlBuilder(core, slug || externalId, raw) || "";
        derivedBy = slug ? "slug_template" : "id_template";
      }
      if (!/^https?:\/\//i.test(String(url || ""))) {
        skipped.push({ id: externalId, reason: "没有能在浏览器里打开的网址" });
        continue;
      }
      const titleHit = findKeyDeep(core, TITLE_KEYS, { scalarOnly: true, maxDepth: 2 });
      const authorHit = findKeyDeep(core, AUTHOR_KEYS, { maxDepth: 2 });
      const authorRaw = authorHit ? authorHit.value : null;
      items.push({
        url,
        external_content_id: externalId.slice(0, 512) || null,
        title: titleHit ? String(titleHit.value).slice(0, 2048) : null,
        author_name: (typeof authorRaw === "string" ? authorRaw
          : authorRaw && typeof authorRaw === "object"
            ? String(authorRaw.nickname || authorRaw.name || authorRaw.user_name
                     || authorRaw.screen_name || authorRaw.username || "")
            : "").slice(0, 1024) || null,
        // **这里也要剥。** raw_metadata 会入库、会出现在导出里，
        // 而签名/token 就在查询串上。同一个泄漏点的第二处——
        // 这个仓在「修一处就当修完了」上栽过四次，这次一起修。
        raw_metadata: { source: "page_response_shape", platform: platform || "",
                        matched_path: best.path, matched_url: safePath(best.url),
                        // 网址是取来的还是拼来的，**留在证据里**——
                        // 全是 id_template 的时候，那批网址一条都没被验证过
                        derived_by: derivedBy },
      });
    }
    return { items, skipped };
  }

  const api = Object.freeze({
    recogniseList, normaliseItems, findArrays, score, safePath, findKeyDeep, atPath,
    MIN_ITEMS, MIN_HOMOGENEITY, MAX_ITEM_DEPTH, ID_KEYS, LINK_KEYS, SLUG_KEYS,
  });
  globalThis.SAListShape = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
