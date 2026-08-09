export const LEGACY_PLATFORM_HOST = "huchuliang-workbench.linzezhang35.chatgpt.site";
export const CANONICAL_WORKBENCH_ORIGIN = "https://mydairy.linzezhang.com";

type WorkbenchQuery = {
  reference?: string;
  view?: string;
};

export function isLegacyPlatformHost(host: string | null | undefined): boolean {
  return host === LEGACY_PLATFORM_HOST;
}

export function canonicalWorkbenchUrl(params: WorkbenchQuery): string {
  const search = new URLSearchParams();
  if (typeof params.reference === "string") search.set("reference", params.reference);
  if (typeof params.view === "string") search.set("view", params.view);
  const query = search.toString();
  return `${CANONICAL_WORKBENCH_ORIGIN}/${query ? `?${query}` : ""}`;
}
