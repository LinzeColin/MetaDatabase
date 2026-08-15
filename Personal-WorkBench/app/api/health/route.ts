import { env } from "@/server/runtime/vps3/env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const result = await env.DB.prepare("SELECT 1 AS ready").first<{ ready: number }>();
    if (result?.ready !== 1) throw new Error("database not ready");
    return Response.json(
      { service: "personal-workbench", ready: true },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      { service: "personal-workbench", ready: false },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
