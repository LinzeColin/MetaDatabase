import { env } from "@/server/runtime/vps3/env";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { apiErrorResponse } from "@/server/http/api";
import { probeStorageBindings } from "@/server/storage/binding-health";

export const runtime = "nodejs";

/**
 * An unlinked, verified-session-only diagnostic for a support replay. The
 * response deliberately contains no account, table, object, or binding data.
 */
export async function GET(request: Request): Promise<Response> {
  try {
    await requireVerifiedSession(createAuth(env), request.headers);
    const data = await probeStorageBindings(env);
    return new Response(
      `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>Storage check</title></head><body data-d1="${data.d1}" data-r2="${data.r2}"><main><h1>Storage binding health</h1><p>D1 and R2 bindings are available.</p></main></body></html>`,
      {
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": "text/html; charset=utf-8",
          "X-Robots-Tag": "noindex, nofollow",
        },
      },
    );
  } catch (error) {
    return apiErrorResponse(error);
  }
}
