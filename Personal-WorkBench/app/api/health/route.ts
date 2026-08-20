import { env } from "@/server/runtime/vps3/env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const started = Date.now();
  try {
    const result = await env.DB.prepare("SELECT 1 AS ready").first<{ ready: number }>();
    const objectRoot = process.env.OBJECT_STORAGE_PATH?.trim();
    return Response.json({
      ready: result?.ready === 1,
      runtime: "vps3-node",
      database: "postgresql",
      objectStorage: objectRoot ? "vps3-filesystem" : "unconfigured",
      latencyMs: Date.now() - started,
    }, {
      status: result?.ready === 1 && objectRoot ? 200 : 503,
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return Response.json({
      ready: false,
      runtime: "vps3-node",
      database: "unavailable",
      objectStorage: process.env.OBJECT_STORAGE_PATH?.trim() ? "vps3-filesystem" : "unconfigured",
      latencyMs: Date.now() - started,
    }, {
      status: 503,
      headers: { "cache-control": "no-store" },
    });
  }
}
