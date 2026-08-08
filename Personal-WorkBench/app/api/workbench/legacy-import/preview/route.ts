import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { previewLegacyImport } from "@/server/data/legacy-import";
import { apiErrorResponse, readJson } from "@/server/http/api";

export const runtime = "edge";

export async function POST(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const body = await readJson(request);
    const result = await previewLegacyImport(env.DB, identity.userId, body);
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
