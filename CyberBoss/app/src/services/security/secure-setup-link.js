"use strict";

// CB-620 / AC-010, AC-011: the one-time token travels in the URL fragment, not
// the path or query. A fragment is never sent in the HTTP request line, never
// reaches a Referer header and never lands in an access log, so the link stays
// single-use in practice as well as in the database.

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,86}$/;
const PURPOSE_PATTERN = /^[a-z_]{3,30}$/;

class SetupLinkError extends Error {
  constructor(code) {
    super(code);
    this.name = "SetupLinkError";
    this.code = code;
  }
}

function requireHttpsOrigin(origin) {
  let url;
  try {
    url = new URL(origin);
  } catch {
    throw new SetupLinkError("ORIGIN_INVALID");
  }
  if (url.protocol !== "https:") {
    throw new SetupLinkError("HTTPS_ORIGIN_REQUIRED");
  }
  if (url.pathname !== "/" || url.search !== "" || url.hash !== "") {
    throw new SetupLinkError("ORIGIN_MUST_BE_BARE");
  }
  if (url.username !== "" || url.password !== "") {
    throw new SetupLinkError("ORIGIN_MUST_NOT_CARRY_CREDENTIALS");
  }
  return url.origin;
}

function buildSecureSetupLink({ origin, token, purpose, path = "/setup" }) {
  const httpsOrigin = requireHttpsOrigin(origin);
  if (typeof token !== "string" || !TOKEN_PATTERN.test(token)) {
    throw new SetupLinkError("OPAQUE_TOKEN_REQUIRED");
  }
  if (typeof purpose !== "string" || !PURPOSE_PATTERN.test(purpose)) {
    throw new SetupLinkError("PURPOSE_REQUIRED");
  }
  if (typeof path !== "string" || !/^\/[A-Za-z0-9/_-]{0,64}$/.test(path)) {
    throw new SetupLinkError("PATH_INVALID");
  }
  const url = new URL(path, httpsOrigin);
  url.hash = `t=${encodeURIComponent(token)}&p=${encodeURIComponent(purpose)}`;
  return url.toString();
}

// Used by the tests and the CB-620 validator to prove the token never appears
// in anything a server or proxy would log.
function tokenAppearsInRequestTarget(link, token) {
  const url = new URL(link);
  return `${url.pathname}${url.search}`.includes(token);
}

function parseSetupFragment(fragment) {
  const raw = String(fragment || "").replace(/^#/, "");
  if (raw.length > 512) {
    throw new SetupLinkError("FRAGMENT_TOO_LARGE");
  }
  const params = new URLSearchParams(raw);
  const token = params.get("t");
  const purpose = params.get("p");
  if (!token || !TOKEN_PATTERN.test(token)) {
    throw new SetupLinkError("OPAQUE_TOKEN_REQUIRED");
  }
  if (!purpose || !PURPOSE_PATTERN.test(purpose)) {
    throw new SetupLinkError("PURPOSE_REQUIRED");
  }
  return Object.freeze({ token, purpose });
}

module.exports = {
  SetupLinkError,
  buildSecureSetupLink,
  parseSetupFragment,
  requireHttpsOrigin,
  tokenAppearsInRequestTarget,
};
