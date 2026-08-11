// Cloudflare's documented test secret validates the dummy token without the
// production action/hostname claims. This compatibility path is available
// only for isolated local browser automation; production secrets keep both
// product-specific checks below.
const CLOUDFLARE_TURNSTILE_ALWAYS_PASS_TEST_SECRET =
  "1x0000000000000000000000000000000AA";

function isLocalDevelopmentOrigin(origin: string): boolean {
  try {
    const url = new URL(origin);
    return url.protocol === "http:"
      && (
        url.hostname === "localhost"
        || url.hostname === "127.0.0.1"
        || url.hostname === "0.0.0.0"
        || url.hostname === "::1"
        || url.hostname === "[::1]"
      );
  } catch {
    return false;
  }
}

function usesLocalTurnstileTestKey(secretKey: string, trustedOrigins: readonly string[]): boolean {
  return secretKey === CLOUDFLARE_TURNSTILE_ALWAYS_PASS_TEST_SECRET
    && trustedOrigins.length > 0
    && trustedOrigins.every(isLocalDevelopmentOrigin);
}

export function expectedTurnstileAction(secretKey: string, trustedOrigins: readonly string[]): string | undefined {
  if (usesLocalTurnstileTestKey(secretKey, trustedOrigins)) return undefined;
  return "workbench_auth";
}

export function allowedTurnstileHostnames(secretKey: string, trustedOrigins: readonly string[]): string[] | undefined {
  if (usesLocalTurnstileTestKey(secretKey, trustedOrigins)) return undefined;
  return [...new Set(trustedOrigins.map((origin) => new URL(origin).hostname))];
}
