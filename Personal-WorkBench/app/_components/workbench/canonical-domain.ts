/**
 * Compatibility-only hostname from the retired product identity. It remains
 * here solely to send existing saved links to the canonical mydairy domain.
 */
export const RETIRED_COMPATIBILITY_HOST = "huchuliang-workbench.linzezhang35.chatgpt.site";
export const CANONICAL_MYDAIRY_ORIGIN = "https://mydairy.linzezhang.com";

export function isRetiredCompatibilityHost(host: string | null | undefined): boolean {
  const normalized = host?.trim().toLowerCase();
  return normalized === RETIRED_COMPATIBILITY_HOST || normalized === `${RETIRED_COMPATIBILITY_HOST}:443`;
}

export function canonicalRetiredHostUrl(
  host: string | null | undefined,
  search = "",
  pathname = "/",
  hash = "",
): string | null {
  if (!isRetiredCompatibilityHost(host)) return null;
  const destination = new URL(CANONICAL_MYDAIRY_ORIGIN);
  destination.pathname = pathname.startsWith("/") ? pathname : "/";
  destination.search = search.startsWith("?") ? search.slice(1) : search;
  destination.hash = hash.startsWith("#") ? hash.slice(1) : hash;
  return destination.toString();
}

export function canonicalRetiredUrl(currentUrl: string): string | null {
  try {
    const url = new URL(currentUrl);
    return canonicalRetiredHostUrl(url.host, url.search, url.pathname, url.hash);
  } catch {
    return null;
  }
}
