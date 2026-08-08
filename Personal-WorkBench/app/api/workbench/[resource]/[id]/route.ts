import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import { beginIdempotentWrite } from "@/server/data/idempotency";
import { getTenantResource, normalizeResourceInput } from "@/server/data/resources";
import {
  deleteTenantRecord,
  getTenantRecord,
  updateTenantRecord,
} from "@/server/data/tenant-store";
import { apiErrorResponse, notFoundResponse, readJson } from "@/server/http/api";
import { writeRedactedSecurityEvent } from "@/server/security/audit";
import { requireSensitiveCloudConsent } from "@/server/security/privacy-consent";

export const runtime = "edge";

type Context = { params: Promise<{ resource: string; id: string }> };

function safeId(value: string): string | null {
  return /^[A-Za-z0-9_-]{1,160}$/.test(value) ? value : null;
}

async function record(userId: string, eventType: string, outcome: "success" | "rejected" | "failed") {
  try {
    await writeRedactedSecurityEvent(env, userId, eventType, outcome);
  } catch {
    // See the redacted audit contract; do not log request content here.
  }
}

async function contextFor(request: Request, context: Context) {
  const identity = await requireVerifiedSession(createAuth(env), request.headers);
  const { resource: resourceName, id: rawId } = await context.params;
  const resource = getTenantResource(resourceName);
  const id = safeId(rawId);
  if (!resource || !id) return { identity, resource: null, resourceName, id: null };
  return { identity, resource, resourceName, id };
}

export async function GET(request: Request, context: Context): Promise<Response> {
  try {
    const current = await contextFor(request, context);
    if (!current.resource || !current.id) return notFoundResponse();
    await requireSensitiveCloudConsent(env.DB, current.identity.userId, current.resourceName);
    const data = await getTenantRecord(env.DB, current.resource, current.identity.userId, current.id);
    if (!data) return notFoundResponse();
    return Response.json({ data }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function PATCH(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  let eventType = "workbench.update";
  try {
    const current = await contextFor(request, context);
    userId = current.identity.userId;
    if (!current.resource || !current.id) return notFoundResponse();
    await requireSensitiveCloudConsent(env.DB, userId, current.resourceName);
    eventType = `workbench.${current.resourceName}.update`;

    const body = await readJson(request);
    const values = normalizeResourceInput(current.resource, body, "update");
    const endpoint = `PATCH:/api/workbench/${current.resourceName}/${current.id}`;
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: values,
    });
    try {
      if (!lease.replayed) {
        await updateTenantRecord(env.DB, current.resource, userId, current.id, values);
      }
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    const data = await getTenantRecord(env.DB, current.resource, userId, current.id);
    if (!data) return notFoundResponse();
    await record(userId, eventType, "success");
    return Response.json({ data, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, eventType, "rejected");
    return apiErrorResponse(error);
  }
}

export async function DELETE(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  let eventType = "workbench.delete";
  try {
    const current = await contextFor(request, context);
    userId = current.identity.userId;
    if (!current.resource || !current.id) return notFoundResponse();
    // Erasure remains available after withdrawal: it removes the caller's own data
    // and never returns or creates new sensitive cloud content.
    eventType = `workbench.${current.resourceName}.delete`;
    const endpoint = `DELETE:/api/workbench/${current.resourceName}/${current.id}`;
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: { id: current.id },
    });
    try {
      if (!lease.replayed) {
        await deleteTenantRecord(env.DB, current.resource, userId, current.id);
      }
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    await record(userId, eventType, "success");
    return Response.json({ deleted: true, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, eventType, "rejected");
    return apiErrorResponse(error);
  }
}
