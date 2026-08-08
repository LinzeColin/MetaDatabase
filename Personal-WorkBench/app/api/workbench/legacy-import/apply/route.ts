import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { beginIdempotentWrite } from "@/server/data/idempotency";
import {
  applyLegacyImport,
  requireLegacyImportConsent,
  validateLegacyEnvelope,
} from "@/server/data/legacy-import";
import { apiErrorResponse, readJson } from "@/server/http/api";

export const runtime = "edge";

export async function POST(request: Request): Promise<Response> {
  let userId: string | null = null;
  const endpoint = "POST:/api/workbench/legacy-import/apply";
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    userId = identity.userId;

    const body = await readJson(request);
    const envelope = validateLegacyEnvelope(body);
    await requireLegacyImportConsent(env.DB, userId, envelope);
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: envelope,
    });

    try {
      const result = await applyLegacyImport(env.DB, userId, envelope);
      await lease.complete();
      return Response.json(result, { headers: { "Cache-Control": "no-store" } });
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
  } catch (error) {
    return apiErrorResponse(error);
  }
}
