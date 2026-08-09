export const LEGACY_PLATFORM_HOST = "huchuliang-workbench.linzezhang35.chatgpt.site";
export const CANONICAL_WORKBENCH_ORIGIN = "https://mydairy.linzezhang.com";

export function isLegacyPlatformHost(host: string | null | undefined): boolean {
  return host === LEGACY_PLATFORM_HOST;
}

export function canonicalLegacyUrl(currentUrl: string): string | null {
  try {
    const url = new URL(currentUrl);
    if (!isLegacyPlatformHost(url.hostname)) return null;
    url.protocol = "https:";
    url.hostname = new URL(CANONICAL_WORKBENCH_ORIGIN).hostname;
    url.port = "";
    return url.toString();
  } catch {
    return null;
  }
}
