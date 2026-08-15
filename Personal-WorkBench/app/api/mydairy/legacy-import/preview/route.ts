import { env } from "@/server/runtime/vps3/env";
import { createAuth } from "@/server/auth";
import { requireVerifiedMutationSession } from "@/server/auth/session";
import {
  previewLegacyImport,
  requireLegacyImportConsent,
  validateLegacyEnvelope,
} from "@/server/data/legacy-import";
import { apiErrorResponse, readJson } from "@/server/http/api";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedMutationSession(createAuth(env), request, env);
    const body = await readJson(request);
    const envelope = validateLegacyEnvelope(body);
    await requireLegacyImportConsent(env.DB, identity.userId, envelope);
    const result = await previewLegacyImport(env.DB, identity.userId, envelope);
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
