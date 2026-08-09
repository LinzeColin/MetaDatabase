import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { apiErrorResponse } from "@/server/http/api";
import { probeStorageBindings } from "@/server/storage/binding-health";

export const runtime = "edge";

/**
 * An unlinked, verified-session-only diagnostic for a support replay. The
 * response deliberately contains no account, table, object, or binding data.
 */
export async function GET(request: Request): Promise<Response> {
  try {
    await requireVerifiedSession(createAuth(env), request.headers);
    const data = await probeStorageBindings(env);
    return Response.json({ data }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
