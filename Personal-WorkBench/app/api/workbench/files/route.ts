import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { beginIdempotentWrite, stableRecordId } from "@/server/data/idempotency";
import { readPrivateFileForm } from "@/server/files/form";
import { createPrivateFile, privateFileExists } from "@/server/files/private-files";
import { apiErrorResponse } from "@/server/http/api";
import { writeRedactedSecurityEvent } from "@/server/security/audit";
import { requireSensitiveCloudConsent } from "@/server/security/privacy-consent";

export const runtime = "edge";

async function record(userId: string, outcome: "success" | "rejected" | "failed") {
  try {
    await writeRedactedSecurityEvent(env, userId, "workbench.file.create", outcome);
  } catch {
    // No content, object key, or recipient metadata is ever logged from this path.
  }
}

export async function POST(request: Request): Promise<Response> {
  let userId: string | null = null;
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    userId = identity.userId;
    const upload = await readPrivateFileForm(request);
    await requireSensitiveCloudConsent(env.DB, userId, upload.module);
    const endpoint = "POST:/api/workbench/files";
    const idempotencyKey = request.headers.get("idempotency-key");
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey,
      payload: {
        module: upload.module,
        contentType: upload.validated.contentType,
        byteSize: upload.validated.byteSize,
        sha256: upload.validated.sha256,
      },
    });
    const id = await stableRecordId(userId, endpoint, idempotencyKey ?? "");
    try {
      if (!lease.replayed && !(await privateFileExists(env, userId, id))) {
        await createPrivateFile(env, { userId, id, ...upload });
      }
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    await record(userId, "success");
    return Response.json(
      { data: { id, module: upload.module, contentType: upload.validated.contentType, byteSize: upload.validated.byteSize }, replayed: lease.replayed },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    if (userId) await record(userId, "rejected");
    return apiErrorResponse(error);
  }
}
