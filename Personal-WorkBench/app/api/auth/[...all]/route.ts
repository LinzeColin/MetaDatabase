import { env } from "cloudflare:workers";
import { AuthRuntimeNotReadyError, createAuth } from "@/server/auth";

export const runtime = "edge";

function unavailableResponse(): Response {
  return Response.json(
    { message: "服务暂时不可用，请稍后再试。" },
    {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

async function handle(request: Request): Promise<Response> {
  try {
    return await createAuth(env).handler(request);
  } catch (error) {
    if (error instanceof AuthRuntimeNotReadyError) return unavailableResponse();

    // Deliberately avoid serializing unexpected provider/database failures.
    return Response.json(
      { message: "服务暂时不可用，请稍后再试。" },
      {
        status: 500,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;

export function OPTIONS(): Response {
  return new Response(null, {
    status: 204,
    headers: { Allow: "GET, POST, PUT, PATCH, DELETE, OPTIONS" },
  });
}
