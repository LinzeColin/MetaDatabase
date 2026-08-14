import { env } from "cloudflare:workers";
import { getPublicAuthPageConfig } from "@/server/auth";

/**
 * The Turnstile site key is intentionally public. Read it during the dynamic
 * server render so normal email auth does not first depend on a second client
 * request before it can display the verification challenge.
 */
export function publicAuthTurnstileSiteKey(): string | null {
  return getPublicAuthPageConfig(env).turnstileSiteKey;
}

/** Google OAuth client IDs are public browser identifiers, never secrets. */
export function publicAuthGoogleClientId(): string | null {
  return getPublicAuthPageConfig(env).googleClientId;
}
