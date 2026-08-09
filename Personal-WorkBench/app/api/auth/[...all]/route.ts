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
    if (error instanceof AuthRuntimeNotReadyError) {
      // This is intentionally value-free operational telemetry. It is never
      // returned to the browser, and must not be expanded with env values,
      // Origins, account data, request headers, or the caught error object.
      console.error("auth_runtime_not_ready", {
        missing_categories: error.missingCategories,
      });
      return unavailableResponse();
    }

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
