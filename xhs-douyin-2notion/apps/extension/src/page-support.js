const RULES = Object.freeze([
  Object.freeze({
    platform: "xiaohongshu",
    hosts: Object.freeze(["xiaohongshu.com", "www.xiaohongshu.com"]),
    paths: Object.freeze([/^\/explore\/[A-Za-z0-9_-]+\/?$/, /^\/discovery\/item\/[A-Za-z0-9_-]+\/?$/]),
  }),
  Object.freeze({
    platform: "douyin",
    hosts: Object.freeze(["douyin.com", "www.douyin.com"]),
    paths: Object.freeze([/^\/video\/[A-Za-z0-9_-]+\/?$/]),
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
    query: (url) => /^[1-9][0-9]{5,20}$/.test(url.searchParams.get("id") ?? ""),
  }),
]);

export const SUPPORTED_PLATFORMS = Object.freeze(RULES.map((rule) => rule.platform));

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
      && (typeof rule.query !== "function" || rule.query(url)),
  );
  if (!match) {
    return Object.freeze({ executable: false, platform: null, reason: "unsupported_page", supported: false });
  }

  return Object.freeze({
    executable: false,
    platform: match.platform,
    reason: "platform_gate_disabled_stage_1",
    supported: true,
  });
}
