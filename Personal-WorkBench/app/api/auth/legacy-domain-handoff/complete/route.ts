import { env } from "@/server/runtime/vps3/env";
import {
  LEGACY_DEVICE_HISTORY_SESSION_KEY,
  serializeLegacyDeviceHistoryPayload,
} from "@/app/_components/workbench/legacy-device-history-payload";
import { createAuth } from "@/server/auth";
import {
  canonicalHandoffDestination,
  consumeLegacyDomainHandoff,
  isCanonicalHandoffCompletionRequest,
  legacyHandoffSessionCookieHeader,
  legacyHandoffSessionHeaders,
  legacyHandoffTarget,
  parseLegacyHandoffId,
  transferableAuthSession,
} from "@/server/auth/legacy-domain-handoff";

export const runtime = "nodejs";

function redirect(targetPath = "/", cookieHeader: string | null = null): Response {
  const headers = new Headers({
    Location: canonicalHandoffDestination(targetPath),
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  });
  if (cookieHeader) headers.append("Set-Cookie", cookieHeader);
  return new Response(null, { status: 303, headers });
}

function scriptString(value: string): string {
  return JSON.stringify(value)
    .replaceAll("<", "\\u003c")
    .replaceAll(">", "\\u003e")
    .replaceAll("&", "\\u0026")
    .replaceAll("\u2028", "\\u2028")
    .replaceAll("\u2029", "\\u2029");
}

/**
 * This is a top-level document, not an iframe: both hosts deliberately deny
 * framing. The payload travels only from the retiring browser origin to this
 * canonical page, is put into same-tab sessionStorage, and is never stored by
 * the worker, D1, or R2.
 */
function historyTransferDocument(
  targetPath: string,
  historyPayload: string,
  cookieHeader: string | null,
): Response {
  const destination = canonicalHandoffDestination(targetPath);
  const headers = new Headers({
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; script-src 'unsafe-inline'",
    "Content-Type": "text/html; charset=utf-8",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  });
  if (cookieHeader) headers.append("Set-Cookie", cookieHeader);
  const script = "try { sessionStorage.setItem(" + scriptString(LEGACY_DEVICE_HISTORY_SESSION_KEY)
    + ", " + scriptString(historyPayload) + "); } catch {}"
    + "window.location.replace(" + scriptString(destination) + ");";
  return new Response("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"></head><body><script>"
    + script + "</script></body></html>", { headers });
}

/** The opaque form value is consumed before any canonical-domain cookie is set. */
export async function POST(request: Request): Promise<Response> {
  try {
    if (!isCanonicalHandoffCompletionRequest(request)) return redirect();
    const form = await request.formData();
    const handoffId = parseLegacyHandoffId(form.get("handoff"));
    const historyPayload = serializeLegacyDeviceHistoryPayload(form.get("history"));
    let targetPath = legacyHandoffTarget(form.get("next"));
    let cookieHeader: string | null = null;

    if (handoffId) {
      const handoff = await consumeLegacyDomainHandoff(env.DB, handoffId);
      if (handoff) {
        targetPath = handoff.targetPath;
        const headers = legacyHandoffSessionHeaders(handoff.sessionCookie);
        if (headers) {
          const session = await createAuth(env).api.getSession({
            headers,
            query: { disableCookieCache: true },
          });
          if (transferableAuthSession(session)) {
            cookieHeader = legacyHandoffSessionCookieHeader(handoff.sessionCookie, session.session.expiresAt);
          }
        }
      }
    }

    return historyPayload
      ? historyTransferDocument(targetPath, historyPayload, cookieHeader)
      : redirect(targetPath, cookieHeader);
  } catch {
    return redirect();
  }
}
