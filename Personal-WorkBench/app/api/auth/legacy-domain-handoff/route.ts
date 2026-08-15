import { env } from "@/server/runtime/vps3/env";
import { createAuth } from "@/server/auth";
import { apiErrorResponse, readJson } from "@/server/http/api";
import {
  isRetiredHandoffIssuanceRequest,
  issueLegacyDomainHandoff,
  legacyHandoffTarget,
  legacySignedSessionCookie,
  transferableAuthSession,
} from "@/server/auth/legacy-domain-handoff";

export const runtime = "nodejs";

function noStore(status = 204): Response {
  return new Response(null, { status, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
}

function requestedTarget(value: unknown): string {
  return value && typeof value === "object" && !Array.isArray(value) && "next" in value
    ? legacyHandoffTarget((value as { next?: unknown }).next)
    : "/";
}

/**
 * This endpoint exists only on the retired hostname. Its response exposes an
 * opaque, short-lived id—not a user id, session cookie, or any business data.
 */
export async function POST(request: Request): Promise<Response> {
  try {
    if (!isRetiredHandoffIssuanceRequest(request)) return noStore(404);
    const session = await createAuth(env).api.getSession({
      headers: request.headers,
      query: { disableCookieCache: true },
    });
    const sessionCookie = legacySignedSessionCookie(request.headers);
    if (!transferableAuthSession(session) || !sessionCookie) return noStore();
    const handoff = await issueLegacyDomainHandoff(env.DB, {
      sessionCookie,
      targetPath: requestedTarget(await readJson(request)),
    });
    return Response.json({ handoff }, {
      headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
