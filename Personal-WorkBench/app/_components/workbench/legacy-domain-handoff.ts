import { safeAccountReturnPath } from "./account-return-path";
import { CANONICAL_MYDAIRY_ORIGIN } from "./canonical-domain";

export const LEGACY_DOMAIN_HANDOFF_COMPLETE_URL = `${CANONICAL_MYDAIRY_ORIGIN}/api/auth/legacy-domain-handoff/complete`;

const HANDOFF_ID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

/** Preserve only a same-origin page path when crossing the retired hostname. */
export function legacyHandoffTarget(value: unknown): string {
  return safeAccountReturnPath(typeof value === "string" ? value : null) ?? "/";
}

export function canonicalHandoffDestination(targetPath: string): string {
  return new URL(legacyHandoffTarget(targetPath), CANONICAL_MYDAIRY_ORIGIN).toString();
}

export function parseLegacyHandoffId(value: unknown): string | null {
  return typeof value === "string" && HANDOFF_ID_PATTERN.test(value) ? value.toLowerCase() : null;
}
