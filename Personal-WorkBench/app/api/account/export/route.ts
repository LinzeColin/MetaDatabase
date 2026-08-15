import { env } from "@/server/runtime/vps3/env";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { getAccountExport, hashAccountExport } from "@/server/data/account-lifecycle";
import { apiErrorResponse } from "@/server/http/api";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const exportData = await getAccountExport(env.DB, identity.userId);
    const exportHash = await hashAccountExport(exportData);
    return Response.json(
      { data: exportData, exportHash },
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
