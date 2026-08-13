import { headers } from "next/headers";
import { isRetiredCompatibilityHost } from "../../_components/workbench/canonical-domain";

/** Resolve the request host on the server before an authentication form renders. */
export async function isRetiredAuthHost(): Promise<boolean> {
  return isRetiredCompatibilityHost((await headers()).get("host"));
}
