import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedMutationSession, requireVerifiedSession } from "@/server/auth/session";
import { beginIdempotentWrite } from "@/server/data/idempotency";
import { ResourceInputError } from "@/server/data/resources";
import { apiErrorResponse, readJson } from "@/server/http/api";
import { writeRedactedSecurityEvent } from "@/server/security/audit";
import { rejectClientTenantFields } from "@/server/security/tenant";

export const runtime = "edge";

type ProfileValues = {
  displayName: string;
  timezone: string;
  locale: "zh-CN" | "en-US";
  showWelcome: boolean;
};

function parseProfile(input: unknown): ProfileValues {
  rejectClientTenantFields(input);
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new ResourceInputError();
  const value = input as Record<string, unknown>;
  if (Object.keys(value).some((key) => !["displayName", "timezone", "locale", "showWelcome"].includes(key))) {
    throw new ResourceInputError();
  }
  if (
    typeof value.displayName !== "string" ||
    value.displayName.trim().length < 1 ||
    value.displayName.trim().length > 80 ||
    typeof value.timezone !== "string" ||
    value.timezone.trim().length < 1 ||
    value.timezone.trim().length > 80 ||
    (value.locale !== "zh-CN" && value.locale !== "en-US") ||
    typeof value.showWelcome !== "boolean"
  ) {
    throw new ResourceInputError();
  }
  return {
    displayName: value.displayName.trim(),
    timezone: value.timezone.trim(),
    locale: value.locale,
    showWelcome: value.showWelcome,
  };
}

async function record(userId: string, outcome: "success" | "rejected") {
  try {
    await writeRedactedSecurityEvent(env, userId, "workbench.profile.update", outcome);
  } catch {
    // Profile contents are never included in the audit event.
  }
}

export async function GET(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const data = await env.DB.prepare(
      `SELECT display_name, timezone, locale, show_welcome, updated_at
       FROM profile_settings WHERE user_id = ? LIMIT 1`,
    )
      .bind(identity.userId)
      .first();
    return Response.json({ data }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function PUT(request: Request): Promise<Response> {
  let userId: string | null = null;
  try {
    const identity = await requireVerifiedMutationSession(createAuth(env), request, env);
    userId = identity.userId;
    const values = parseProfile(await readJson(request));
    const endpoint = "PUT:/api/workbench/profile";
    const lease = await beginIdempotentWrite(env.DB, {
      userId,
      endpoint,
      idempotencyKey: request.headers.get("idempotency-key"),
      payload: values,
    });
    try {
      if (!lease.replayed) {
        const now = Date.now();
        await env.DB.prepare(
          `INSERT INTO profile_settings
            (user_id, display_name, timezone, locale, show_welcome, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
            display_name = excluded.display_name,
            timezone = excluded.timezone,
            locale = excluded.locale,
            show_welcome = excluded.show_welcome,
            updated_at = excluded.updated_at`,
        )
          .bind(userId, values.displayName, values.timezone, values.locale, values.showWelcome ? 1 : 0, now, now)
          .run();
      }
      await lease.complete();
    } catch (error) {
      await lease.fail().catch(() => undefined);
      throw error;
    }
    await record(userId, "success");
    return Response.json({ data: values, replayed: lease.replayed }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (userId) await record(userId, "rejected");
    return apiErrorResponse(error);
  }
}
