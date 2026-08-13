import {
  CANONICAL_MYDAIRY_ORIGIN,
  isRetiredCompatibilityHost,
} from "../../_components/workbench/canonical-domain";

export const runtime = "edge";

/**
 * Compatibility for saved links from the earlier authentication URL. Keep the
 * redirect same-origin (or canonical for the retired host), avoid forwarding
 * arbitrary query data, and let the current sign-in screen own every login
 * interaction.
 */
function signInLocation(request: Request): URL | null {
  try {
    const current = new URL(request.url);
    return new URL(
      "/auth/sign-in",
      isRetiredCompatibilityHost(current.host) ? CANONICAL_MYDAIRY_ORIGIN : current.origin,
    );
  } catch {
    return null;
  }
}

function redirectToSignIn(request: Request): Response {
  const location = signInLocation(request);
  if (!location) return new Response(null, { status: 400 });
  return new Response(null, {
    status: 302,
    headers: {
      "Cache-Control": "no-store",
      Location: location.toString(),
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex",
    },
  });
}

export function GET(request: Request): Response {
  return redirectToSignIn(request);
}

export function HEAD(request: Request): Response {
  return redirectToSignIn(request);
}
