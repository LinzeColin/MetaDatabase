import { env } from "@/server/runtime/vps3/env";
import { getPublicAuthPageConfig } from "@/server/auth";

export const runtime = "nodejs";

/** Turnstile site keys are public by design; no secret or provider detail is exposed. */
export function GET(): Response {
  return Response.json(getPublicAuthPageConfig(env), {
    headers: { "Cache-Control": "no-store" },
  });
}
