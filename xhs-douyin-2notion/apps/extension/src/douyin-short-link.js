const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/u;
const REDIRECT_STATUSES = Object.freeze(new Set([301, 302, 303, 307, 308]));
const ALLOWED_HOSTS = Object.freeze(new Set(["v.douyin.com", "www.douyin.com"]));

function exactKeys(value, expected) {
  return JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

export class DouyinShortLinkError extends Error {
  constructor(code) {
    super(code);
    this.name = "DouyinShortLinkError";
    this.code = code;
  }
}

function inspectUrl(raw, base) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 2_048) {
    throw new DouyinShortLinkError("X2N_SHORTLINK_URL_INVALID");
  }
  let value;
  try {
    value = new URL(raw, base);
  } catch {
    throw new DouyinShortLinkError("X2N_SHORTLINK_URL_INVALID");
  }
  if (
    value.protocol !== "https:"
    || value.username
    || value.password
    || value.port
    || !ALLOWED_HOSTS.has(value.hostname.toLowerCase())
  ) throw new DouyinShortLinkError("X2N_SHORTLINK_HOST_BLOCKED");
  value.hash = "";
  return value;
}

function detailIdentity(value) {
  if (value.hostname.toLowerCase() !== "www.douyin.com") return null;
  const match = value.pathname.match(/^\/(video|note)\/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\/?$/u);
  if (!match || !SAFE_ID.test(match[2]) || !match[2].startsWith("synthetic-")) return null;
  return { contentId: match[2], contentKind: match[1] };
}

function safeHop(value) {
  if (detailIdentity(value)) return true;
  return value.hostname.toLowerCase() === "v.douyin.com"
    && /^\/synthetic-[A-Za-z0-9_-]+\/?$/u.test(value.pathname);
}

function canonicalPageUrl(identity) {
  return ["https:", "", "www.douyin.com", identity.contentKind, identity.contentId].join("/");
}

/**
 * Resolves one synthetic/injected manual-redirect transport. Product code does
 * not provide a network transport until a later policy/auth gate authorizes it.
 */
export async function resolveDouyinShortLink(rawUrl, requestHop, options = {}) {
  if (typeof requestHop !== "function") throw new TypeError("A manual redirect requester is required");
  const maxRedirects = options.maxRedirects ?? 3;
  if (!Number.isSafeInteger(maxRedirects) || maxRedirects < 1 || maxRedirects > 5) {
    throw new TypeError("Invalid redirect limit");
  }
  let current = inspectUrl(rawUrl);
  if (current.hostname.toLowerCase() !== "v.douyin.com"
    || !/^\/synthetic-[A-Za-z0-9_-]+\/?$/u.test(current.pathname)) {
    throw new DouyinShortLinkError("X2N_SHORTLINK_START_INVALID");
  }
  current.search = "";
  const visited = new Set();

  for (let redirectCount = 0; redirectCount <= maxRedirects; redirectCount += 1) {
    const currentKey = current.toString();
    if (visited.has(currentKey)) throw new DouyinShortLinkError("X2N_SHORTLINK_REDIRECT_LOOP");
    visited.add(currentKey);
    const direct = detailIdentity(current);
    if (direct) {
      return {
        content_id: direct.contentId,
        content_kind: direct.contentKind,
        page_url: canonicalPageUrl(direct),
        redirect_count: redirectCount,
        status: "resolved",
      };
    }
    if (redirectCount === maxRedirects) throw new DouyinShortLinkError("X2N_SHORTLINK_REDIRECT_LIMIT");

    let response;
    try {
      response = await requestHop(Object.freeze({
        cache: "no-store",
        credentials: "omit",
        method: "HEAD",
        redirect: "manual",
        referrerPolicy: "no-referrer",
        url: currentKey,
      }));
    } catch {
      throw new DouyinShortLinkError("X2N_SHORTLINK_REQUEST_FAILED");
    }
    if (
      response === null
      || typeof response !== "object"
      || Array.isArray(response)
      || !exactKeys(response, ["location", "status"])
    ) {
      throw new DouyinShortLinkError("X2N_SHORTLINK_RESPONSE_INVALID");
    }
    if (!Number.isSafeInteger(response.status) || !REDIRECT_STATUSES.has(response.status)) {
      throw new DouyinShortLinkError("X2N_SHORTLINK_STATUS_BLOCKED");
    }
    if (typeof response.location !== "string" || response.location.length === 0 || response.location.length > 2_048) {
      throw new DouyinShortLinkError("X2N_SHORTLINK_LOCATION_INVALID");
    }
    current = inspectUrl(response.location, currentKey);
    if (!safeHop(current)) throw new DouyinShortLinkError("X2N_SHORTLINK_PATH_BLOCKED");
    if (current.hostname.toLowerCase() === "v.douyin.com") current.search = "";
  }
  throw new DouyinShortLinkError("X2N_SHORTLINK_REDIRECT_LIMIT");
}
