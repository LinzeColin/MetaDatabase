/**
 * Keep every first-party Better Auth session-cookie consumer aligned with the
 * product's configured namespace.  The retired-domain handoff must use the
 * same name as Better Auth itself, otherwise a valid old-domain session is
 * silently treated as anonymous after the canonical-domain migration.
 */
export const AUTH_COOKIE_PREFIX = "hcl-workbench";
export const AUTH_SESSION_COOKIE_NAME = `${AUTH_COOKIE_PREFIX}.session_token`;
export const SECURE_AUTH_SESSION_COOKIE_NAME = `__Secure-${AUTH_SESSION_COOKIE_NAME}`;
