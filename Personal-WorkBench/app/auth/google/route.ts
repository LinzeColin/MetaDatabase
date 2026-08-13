import { env } from "cloudflare:workers";
import { AUTHENTICATED_HOME_PATH } from "../_components/auth-flow";
import {
  CANONICAL_MYDAIRY_ORIGIN,
  isRetiredCompatibilityHost,
} from "../../_components/workbench/canonical-domain";
import { createAuth } from "@/server/auth";

export const runtime = "edge";

type SocialStartPayload = {
  url?: unknown;
};

function signInFailure(requestUrl: URL): Response {
  const destination = new URL("/auth/sign-in?auth_error=1", requestUrl.origin);
  return redirect(destination);
}

function redirect(destination: URL): Response {
  return new Response(null, {
    status: 302,
    headers: {
      "Cache-Control": "no-store",
      Location: destination.toString(),
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex",
    },
  });
}

/**
 * Starts the same fixed Google flow as the enhanced client button, but from a
 * normal same-origin navigation. This is intentionally a GET with no caller
 * supplied callback target: if script hydration is delayed or unavailable,
 * the visitor can still reach Google without opening an arbitrary redirect.
 */
export async function GET(request: Request): Promise<Response> {
  let requestUrl: URL;
  try {
    requestUrl = new URL(request.url);
  } catch {
    return new Response(null, { status: 400 });
  }

  if (isRetiredCompatibilityHost(requestUrl.host)) {
    return redirect(new URL("/auth/sign-in", CANONICAL_MYDAIRY_ORIGIN));
  }

  try {
    const headers = new Headers({
      "Content-Type": "application/json",
      Origin: requestUrl.origin,
    });
    const cookie = request.headers.get("cookie");
    if (cookie) headers.set("Cookie", cookie);
    // The fallback route is only a transport bridge. Preserve the trusted
    // Cloudflare client address so Better Auth keeps the same per-visitor rate
    // limiting behaviour as the enhanced client request.
    const clientIp = request.headers.get("cf-connecting-ip");
    if (clientIp) headers.set("cf-connecting-ip", clientIp);

    const start = await createAuth(env).handler(new Request(
      new URL("/api/auth/sign-in/social", requestUrl.origin),
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          provider: "google",
          callbackURL: AUTHENTICATED_HOME_PATH,
        }),
      },
    ));
    const payload = await start.json().catch(() => null) as SocialStartPayload | null;
    if (!start.ok || typeof payload?.url !== "string") return signInFailure(requestUrl);

    const authorizationUrl = new URL(payload.url);
    if (authorizationUrl.protocol !== "https:") return signInFailure(requestUrl);

    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      Location: authorizationUrl.toString(),
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex",
    });
    // The authorization state is a short-lived, HttpOnly first-party cookie.
    // It must survive this navigation exactly as it does for the JS request.
    const stateCookie = start.headers.get("set-cookie");
    if (stateCookie) responseHeaders.set("Set-Cookie", stateCookie);
    return new Response(null, { status: 302, headers: responseHeaders });
  } catch {
    return signInFailure(requestUrl);
  }
}
