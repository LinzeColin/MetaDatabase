import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import {
  canonicalHandoffDestination,
  consumeLegacyDomainHandoff,
  isCanonicalHandoffCompletionRequest,
  legacyHandoffSessionCookieHeader,
  legacyHandoffSessionHeaders,
  parseLegacyHandoffId,
  transferableAuthSession,
} from "@/server/auth/legacy-domain-handoff";

export const runtime = "edge";

function redirect(targetPath = "/", cookieHeader: string | null = null): Response {
  const headers = new Headers({
    Location: canonicalHandoffDestination(targetPath),
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  });
  if (cookieHeader) headers.append("Set-Cookie", cookieHeader);
  return new Response(null, { status: 303, headers });
}

/** The opaque form value is consumed before any canonical-domain cookie is set. */
export async function POST(request: Request): Promise<Response> {
  try {
    if (!isCanonicalHandoffCompletionRequest(request)) return redirect();
    const handoffId = parseLegacyHandoffId((await request.formData()).get("handoff"));
    if (!handoffId) return redirect();
    const handoff = await consumeLegacyDomainHandoff(env.DB, handoffId);
    if (!handoff) return redirect();
    const headers = legacyHandoffSessionHeaders(handoff.sessionCookie);
    if (!headers) return redirect(handoff.targetPath);
    const session = await createAuth(env).api.getSession({
      headers,
      query: { disableCookieCache: true },
    });
    if (!transferableAuthSession(session)) return redirect(handoff.targetPath);
    return redirect(
      handoff.targetPath,
      legacyHandoffSessionCookieHeader(handoff.sessionCookie, session.session.expiresAt),
    );
  } catch {
    return redirect();
  }
}
