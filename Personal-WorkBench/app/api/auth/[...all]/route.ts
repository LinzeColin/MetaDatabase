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

type UnexpectedAuthFailureCategory =
  | "database"
  | "authentication_library"
  | "provider"
  | "runtime"
  | "unknown";

function classifyUnexpectedAuthFailure(error: unknown): UnexpectedAuthFailureCategory {
  const signal = `${safeErrorName(error) ?? ""} ${safeErrorCode(error) ?? ""}`.toLowerCase();
  if (/d1|sqlite|sql|drizzle|database/.test(signal)) return "database";
  if (/better.?auth|session|account/.test(signal)) return "authentication_library";
  if (/oauth|google|turnstile|captcha|mail|resend|nitrosend/.test(signal)) return "provider";
  if (/binding|module|import|worker|environment|runtime/.test(signal)) return "runtime";
  return "unknown";
}

function safeErrorName(error: unknown): string | null {
  if (!(error instanceof Error)) return null;
  return /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(error.name) ? error.name : null;
}

function safeErrorCode(error: unknown): string | null {
  if (!error || typeof error !== "object" || !("code" in error)) return null;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" && /^[A-Z][A-Z0-9_]{0,63}$/.test(code) ? code : null;
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

    // Classify only within the worker and never serialize the exception,
    // message, request, user data, Origin, or any configuration value.
    console.error("auth_handler_unexpected_error", {
      category: classifyUnexpectedAuthFailure(error),
      error_name: safeErrorName(error) ?? typeof error,
      error_code: safeErrorCode(error),
    });

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
