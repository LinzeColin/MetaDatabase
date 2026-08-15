import { env } from "@/server/runtime/vps3/env";
import {
  CANONICAL_MYDAIRY_ORIGIN,
  isRetiredCompatibilityHost,
} from "../../_components/workbench/canonical-domain";
import { createAuth } from "../../../server/auth";
import { configuredAuthOrigin } from "../../../server/auth/request-origin";

export const runtime = "nodejs";

function redirect(destination: URL, setCookie?: string | null): Response {
  const headers = new Headers({
    "Cache-Control": "no-store",
    Location: destination.toString(),
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex",
  });
  if (setCookie) headers.set("Set-Cookie", setCookie);
  return new Response(null, {
    status: 302,
    headers,
  });
}

function authorizationUrlFrom(value: unknown): URL | null {
  if (!value || typeof value !== "object") return null;
  const rawUrl = (value as { url?: unknown }).url;
  if (typeof rawUrl !== "string") return null;
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:" && url.hostname === "accounts.google.com" ? url : null;
  } catch {
    return null;
  }
}

function unavailableRedirect(origin: string): Response {
  return redirect(new URL("/auth/sign-in?auth_error=1", origin));
}

/**
 * A direct Google link starts Better Auth's existing OAuth code flow on the
 * server. This keeps the OAuth state cookie and Google redirect available even
 * when the browser identity button or client hydration is unavailable.
 */
export async function GET(request: Request): Promise<Response> {
  let requestUrl: URL;
  try {
    requestUrl = new URL(request.url);
  } catch {
    return new Response(null, { status: 400 });
  }

  const publicOrigin = configuredAuthOrigin(env.APP_ORIGIN) ?? requestUrl.origin;

  if (isRetiredCompatibilityHost(requestUrl.host)) {
    // The OAuth state cookie must be issued by the canonical host because the
    // registered callback returns there. Redirect before starting OAuth so an
    // old saved link cannot create state on the retired hostname.
    return redirect(new URL("/auth/google", CANONICAL_MYDAIRY_ORIGIN));
  }

  const headers = new Headers({
    "Content-Type": "application/json",
    Origin: publicOrigin,
  });
  const connectingIp = request.headers.get("cf-connecting-ip");
  if (connectingIp) headers.set("cf-connecting-ip", connectingIp);

  let authResponse: Response;
  try {
    authResponse = await createAuth(env).handler(new Request(
      new URL("/api/auth/sign-in/social", publicOrigin),
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          provider: "google",
          callbackURL: new URL("/?view=home&auth_return=1", publicOrigin).toString(),
        }),
      },
    ));
  } catch {
    return unavailableRedirect(publicOrigin);
  }

  if (!authResponse.ok) return unavailableRedirect(publicOrigin);

  let authorizationUrl: URL | null = null;
  try {
    authorizationUrl = authorizationUrlFrom(await authResponse.json());
  } catch {
    return unavailableRedirect(publicOrigin);
  }

  return authorizationUrl
    ? redirect(authorizationUrl, authResponse.headers.get("set-cookie"))
    : unavailableRedirect(publicOrigin);
}
