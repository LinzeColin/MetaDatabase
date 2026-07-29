'use strict';
function buildSecureSetupLink({ origin, token, purpose }) {
  const url = new URL('/setup', origin);
  if (url.protocol !== 'https:') throw new TypeError('https origin required');
  if (!/^[A-Za-z0-9_-]{20,}$/.test(token || '')) throw new TypeError('opaque token required');
  if (!/^[a-z_]{3,30}$/.test(purpose || '')) throw new TypeError('purpose required');
  // Fragment is not sent in HTTP request lines or Referer headers. The page exchanges it by POST then clears it.
  url.hash = `t=${encodeURIComponent(token)}&p=${encodeURIComponent(purpose)}`;
  return url.toString();
}
function tokenAppearsInRequestTarget(link, token) {
  const url = new URL(link);
  return `${url.pathname}${url.search}`.includes(token);
}
module.exports = { buildSecureSetupLink, tokenAppearsInRequestTarget };
