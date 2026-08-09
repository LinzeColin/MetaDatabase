export const LEGACY_PLATFORM_HOST = "huchuliang-workbench.linzezhang35.chatgpt.site";
export const CANONICAL_WORKBENCH_ORIGIN = "https://mydairy.linzezhang.com";

export function isLegacyPlatformHost(host: string | null | undefined): boolean {
  const normalized = host?.trim().toLowerCase();
  return normalized === LEGACY_PLATFORM_HOST || normalized === `${LEGACY_PLATFORM_HOST}:443`;
}

export function canonicalLegacyHostUrl(host: string | null | undefined, search = ""): string | null {
  if (!isLegacyPlatformHost(host)) return null;
  const destination = new URL(CANONICAL_WORKBENCH_ORIGIN);
  destination.search = search.startsWith("?") ? search.slice(1) : search;
  return destination.toString();
}

export function canonicalLegacyUrl(currentUrl: string): string | null {
  try {
    const url = new URL(currentUrl);
    return canonicalLegacyHostUrl(url.host, url.search);
  } catch {
    return null;
  }
}
