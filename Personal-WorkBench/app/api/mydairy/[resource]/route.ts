import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedMutationSession, requireVerifiedSession } from "@/server/auth/session";
import {
  beginIdempotentWrite,
  stableRecordId,
} from "@/server/data/idempotency";
import { getTenantResource, normalizeResourceInput } from "@/server/data/resources";
import {
  createTenantRecord,
  getTenantRecord,
  listTenantRecords,
} from "@/server/data/tenant-store";
import { apiErrorResponse, notFoundResponse, readIdempotencyKey, readJson } from "@/server/http/api";
import { writeRedactedSecurityEvent } from "@/server/security/audit";
import { requireSensitiveCloudConsent } from "@/server/security/privacy-consent";

export const runtime = "edge";

type Context = { params: Promise<{ resource: string }> };

async function record(userId: string, eventType: string, outcome: "success" | "rejected" | "failed") {
  try {
    await writeRedactedSecurityEvent(env, userId, eventType, outcome);
  } catch {
    // Audit storage must not turn a safe data response into an error or log PII.
  }
}

export async function GET(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    userId = identity.userId;
    const { resource: resourceName } = await context.params;
    const resource = getTenantResource(resourceName);
    if (!resource) return notFoundResponse();
    await requireSensitiveCloudConsent(env.DB, userId, resourceName);
    const data = await listTenantRecords(env.DB, resource, userId);
    return Response.json({ data }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(request: Request, context: Context): Promise<Response> {
  let userId: string | null = null;
  let eventType = "workbench.create";
  try {
    // Session and verified identity are intentionally established before parsing input.
    const identity = await requireVerifiedMutationSession(createAuth(env), request, env);
    userId = identity.userId;
    const { resource: resourceName } = await context.params;
    const resource = getTenantResource(resourceName);
    if (!resource) return notFoundResponse();
    await requireSensitiveCloudConsent(env.DB, userId, resourceName);
    eventType = `workbench.${resourceName}.create`;

    const body = await readJson(request);
    const values = normalizeResourceInput(resource, body, "create");
    const endpoint = `POST:/api/mydairy/${resourceName}`;
    const idempotencyKey = readIdempotencyKey(request);
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey,
      payload: values,
    });
    const id = await stableRecordId(userId, endpoint, idempotencyKey ?? "");

    try {
      if (!lease.replayed && !(await getTenantRecord(env.DB, resource, userId, id))) {
        await createTenantRecord(env.DB, resource, userId, id, values);
      }
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }

    const data = await getTenantRecord(env.DB, resource, userId, id);
    if (!data) return notFoundResponse();
    await record(userId, eventType, "success");
    return Response.json({ data, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, eventType, "rejected");
    return apiErrorResponse(error);
  }
}
