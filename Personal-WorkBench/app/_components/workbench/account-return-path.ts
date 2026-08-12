type BrowserLocation = {
  hash: string;
  pathname: string;
  search: string;
};

const returnOrigin = "https://mydairy-return.invalid";

/** Only retain a relative same-origin route after an account-setting action. */
export function safeAccountReturnPath(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  try {
    const parsed = new URL(value, returnOrigin);
    if (parsed.origin !== returnOrigin || !parsed.pathname.startsWith("/")) return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

export function accountReturnPathFromLocation(location: BrowserLocation): string {
  return safeAccountReturnPath(`${location.pathname}${location.search}${location.hash}`) ?? "/";
}
