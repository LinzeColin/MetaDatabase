import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { getDeletionState, processDeleteRequest } from "@/server/data/account-lifecycle";
import { apiErrorResponse, readJson } from "@/server/http/api";

export const runtime = "edge";

export async function GET(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const deletion = await getDeletionState(env.DB, identity.userId);
    return Response.json(
      deletion,
      {
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": "application/json; charset=utf-8",
        },
      },
    );
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const result = await processDeleteRequest(env.DB, env, identity.userId, await readJson(request));
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
