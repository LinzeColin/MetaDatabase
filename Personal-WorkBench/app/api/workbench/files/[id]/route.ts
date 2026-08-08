import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { beginIdempotentWrite } from "@/server/data/idempotency";
import { readPrivateFileForm } from "@/server/files/form";
import {
  deletePrivateFile,
  getPrivateFile,
  requirePrivateFileCloudConsent,
  replacePrivateFile,
} from "@/server/files/private-files";
import { apiErrorResponse, notFoundResponse } from "@/server/http/api";
import { writeRedactedSecurityEvent } from "@/server/security/audit";

export const runtime = "edge";

type Context = { params: Promise<{ id: string }> };

function safeId(value: string): string | null {
  return /^[A-Za-z0-9_-]{1,160}$/.test(value) ? value : null;
}

async function record(userId: string, event: "replace" | "delete", outcome: "success" | "rejected" | "failed") {
  try {
    await writeRedactedSecurityEvent(env, userId, `workbench.file.${event}`, outcome);
  } catch {
    // The audit row is intentionally content-free.
  }
}

export async function GET(request: Request, context: Context): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const { id: rawId } = await context.params;
    const id = safeId(rawId);
    if (!id) return notFoundResponse();
    const file = await getPrivateFile(env, identity.userId, id);
    return new Response(file.object.body, {
      headers: {
        "Content-Type": file.contentType,
        "Content-Length": String(file.byteSize),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function PUT(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    userId = identity.userId;
    const { id: rawId } = await context.params;
    const id = safeId(rawId);
    if (!id) return notFoundResponse();
    await requirePrivateFileCloudConsent(env, userId, id);
    const upload = await readPrivateFileForm(request);
    const endpoint = `PUT:/api/workbench/files/${id}`;
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: {
        contentType: upload.validated.contentType,
        byteSize: upload.validated.byteSize,
        sha256: upload.validated.sha256,
      },
    });
    try {
      if (!lease.replayed) await replacePrivateFile(env, { userId, id, buffer: upload.buffer, validated: upload.validated });
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    await record(userId, "replace", "success");
    return Response.json({ data: { id, contentType: upload.validated.contentType, byteSize: upload.validated.byteSize }, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, "replace", "rejected");
    return apiErrorResponse(error);
  }
}

export async function DELETE(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    userId = identity.userId;
    const { id: rawId } = await context.params;
    const id = safeId(rawId);
    if (!id) return notFoundResponse();
    // Deleting a caller-owned object remains available after withdrawal.
    const endpoint = `DELETE:/api/workbench/files/${id}`;
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: { id },
    });
    try {
      if (!lease.replayed) await deletePrivateFile(env, userId, id);
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    await record(userId, "delete", "success");
    return Response.json({ deleted: true, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, "delete", "rejected");
    return apiErrorResponse(error);
  }
}
