export const RETIRED_COMPATIBILITY_HOST = "";
export const CANONICAL_MYDAIRY_ORIGIN = "https://mydairy.linzezhang.com";

export function isRetiredCompatibilityHost(_host: string | null | undefined): boolean {
  return false;
}

export function canonicalRetiredHostUrl(
  _host: string | null | undefined,
  _search = "",
  _pathname = "/",
  _hash = "",
): string | null {
  return null;
}

export function canonicalRetiredUrl(_currentUrl: string): string | null {
  return null;
}
