import { env } from "@/server/runtime/vps3/env";
import { createAuth } from "@/server/auth";
import { requireVerifiedMutationSession } from "@/server/auth/session";
import { beginIdempotentWrite } from "@/server/data/idempotency";
import {
  applyLegacyImport,
  requireLegacyImportConsent,
  validateLegacyEnvelope,
} from "@/server/data/legacy-import";
import { apiErrorResponse, readIdempotencyKey, readJson } from "@/server/http/api";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  let userId: string | null = null;
  const endpoint = "POST:/api/mydairy/legacy-import/apply";
  try {
    const identity = await requireVerifiedMutationSession(createAuth(env), request, env);
    userId = identity.userId;

    const body = await readJson(request);
    const envelope = validateLegacyEnvelope(body);
    await requireLegacyImportConsent(env.DB, userId, envelope);
    const idempotencyKey = readIdempotencyKey(request);
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey,
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
