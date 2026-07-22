const RULES = Object.freeze([
  Object.freeze({
    platform: "xiaohongshu",
    hosts: Object.freeze(["xiaohongshu.com", "www.xiaohongshu.com"]),
    paths: Object.freeze([/^\/explore\/[A-Za-z0-9_-]+\/?$/, /^\/discovery\/item\/[A-Za-z0-9_-]+\/?$/]),
  }),
  Object.freeze({
    platform: "douyin",
    hosts: Object.freeze(["v.douyin.com", "www.douyin.com"]),
    paths: Object.freeze([
      /^\/video\/[A-Za-z0-9_-]+\/?$/,
      /^\/note\/synthetic-[A-Za-z0-9_-]+\/?$/,
      /^\/synthetic-[A-Za-z0-9_-]+\/?$/,
    ]),
    validate: (url) => {
      const host = url.hostname.toLowerCase();
      if (host === "v.douyin.com") return /^\/synthetic-[A-Za-z0-9_-]+\/?$/.test(url.pathname);
      if (url.pathname.startsWith("/note/")) return /^\/note\/synthetic-[A-Za-z0-9_-]+\/?$/.test(url.pathname);
      return /^\/video\/[A-Za-z0-9_-]+\/?$/.test(url.pathname);
    },
  }),
  Object.freeze({
    platform: "bilibili",
    hosts: Object.freeze(["bilibili.com", "www.bilibili.com"]),
    paths: Object.freeze([/^\/video\/[A-Za-z0-9_-]+\/?$/, /^\/read\/[A-Za-z0-9_-]+\/?$/]),
  }),
  Object.freeze({
    platform: "kuaishou",
    hosts: Object.freeze(["kuaishou.com", "www.kuaishou.com"]),
    paths: Object.freeze([/^\/short-video\/[A-Za-z0-9_-]+\/?$/]),
  }),
  Object.freeze({
    platform: "weibo",
    hosts: Object.freeze(["weibo.com", "www.weibo.com"]),
    paths: Object.freeze([/^\/detail\/[A-Za-z0-9_-]+\/?$/, /^\/[0-9]+\/[A-Za-z0-9_-]+\/?$/]),
  }),
  Object.freeze({
    platform: "taobao",
    hosts: Object.freeze(["item.taobao.com"]),
    paths: Object.freeze([/^\/item\.htm\/?$/]),
    validate: (url) => /^[1-9][0-9]{5,20}$/.test(url.searchParams.get("id") ?? ""),
  }),
]);

export const SUPPORTED_PLATFORMS = Object.freeze(RULES.map((rule) => rule.platform));
export const CURRENT_PAGE_FEATURES = Object.freeze({
  bilibili: "ci_synth_only",
  douyin: "ci_synth_only",
  kuaishou: "ci_synth_only",
  taobao: false,
  weibo: "ci_synth_only",
  xiaohongshu: "ci_synth_only",
});

const WEIBO_ARBITRARY_URL_KEYS = Object.freeze(new Set([
  "callback",
  "continue",
  "dest",
  "destination",
  "next",
  "proxy",
  "redirect",
  "redirect_url",
  "return_url",
  "target",
  "uri",
  "url",
]));

function hasWeiboArbitraryUrlControl(url) {
  return [...url.searchParams.keys()].some((key) => WEIBO_ARBITRARY_URL_KEYS.has(key.toLowerCase()));
}

function currentPageExecutable(match, url) {
  const mode = CURRENT_PAGE_FEATURES[match.platform];
  if (mode === true) return true;
  if (
    mode !== "ci_synth_only"
    || !new Set(["bilibili", "douyin", "kuaishou", "weibo", "xiaohongshu"]).has(match.platform)
  ) return false;
  const contentId = url.pathname.split("/").filter(Boolean).at(-1) ?? "";
  if (match.platform === "douyin") return contentId.startsWith("synthetic-");
  if (match.platform === "bilibili") {
    if (url.hostname.toLowerCase() !== "www.bilibili.com" || url.searchParams.has("p")) return false;
    if (url.pathname.startsWith("/video/")) return contentId.startsWith("synthetic-bili-video-");
    return contentId.startsWith("synthetic-bili-article-");
  }
  if (match.platform === "kuaishou") {
    return url.hostname.toLowerCase() === "www.kuaishou.com"
      && contentId.startsWith("synthetic-ks-video-");
  }
  if (match.platform === "weibo") {
    return url.hostname.toLowerCase() === "www.weibo.com"
      && url.pathname.startsWith("/detail/")
      && contentId.startsWith("synthetic-wb-status-")
      && url.search === ""
      && url.hash === "";
  }
  return contentId.startsWith("synthetic-") || contentId.startsWith("synthetic_");
}

function disabledReason(match, url) {
  if (match.platform === "bilibili") {
    if (url.hostname.toLowerCase() !== "www.bilibili.com") return "bilibili_noncanonical_host_disabled";
    if (url.searchParams.has("p")) return "bilibili_semantic_query_unsupported";
    return "bilibili_policy_unknown_real_page_disabled";
  }
  if (match.platform === "kuaishou") {
    if (url.hostname.toLowerCase() !== "www.kuaishou.com") return "kuaishou_noncanonical_host_disabled";
    return "kuaishou_oauth_scope_missing_blocked_auth";
  }
  if (match.platform === "weibo") {
    if (url.hostname.toLowerCase() !== "www.weibo.com") return "weibo_noncanonical_host_disabled";
    if (hasWeiboArbitraryUrlControl(url)) return "weibo_arbitrary_url_control_rejected";
    if (url.search || url.hash) return "weibo_query_fragment_unsupported";
    return "weibo_budget_zero_quota_unknown_disabled";
  }
  return "platform_gate_disabled";
}

export function recognizePage(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.length === 0) {
    return Object.freeze({
      executable: false,
      platform: null,
      reason: "active_tab_url_unavailable",
      supported: false,
    });
  }

  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return Object.freeze({ executable: false, platform: null, reason: "invalid_url", supported: false });
  }

  if (url.protocol !== "https:" || url.username || url.password || url.port) {
    return Object.freeze({ executable: false, platform: null, reason: "unsafe_url", supported: false });
  }

  const host = url.hostname.toLowerCase();
  const match = RULES.find(
    (rule) =>
      rule.hosts.includes(host)
      && rule.paths.some((pathPattern) => pathPattern.test(url.pathname))
      && (typeof rule.validate !== "function" || rule.validate(url)),
  );
  if (!match) {
    return Object.freeze({ executable: false, platform: null, reason: "unsupported_page", supported: false });
  }

  const executable = currentPageExecutable(match, url);
  return Object.freeze({
    executable,
    platform: match.platform,
    reason: executable ? "current_page_ci_synth_enabled" : disabledReason(match, url),
    supported: true,
  });
}
