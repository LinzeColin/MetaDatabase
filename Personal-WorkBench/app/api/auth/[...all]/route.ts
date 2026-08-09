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

type DatabaseFailureReason =
  | "missing_table"
  | "missing_column"
  | "binding_or_transport"
  | "query_or_constraint"
  | "other";

function messageForClassification(error: unknown): string {
  // Read the native Error own-property only to reduce it to a fixed telemetry
  // enum below. The message itself must never be written to a response or log.
  const value = error instanceof Error
    ? Object.getOwnPropertyDescriptor(error, "message")?.value
    : null;
  return typeof value === "string" ? value.toLowerCase() : "";
}

function classifyUnexpectedAuthFailure(error: unknown): UnexpectedAuthFailureCategory {
  // Stack text is inspected only to select one of the fixed categories below.
  // It is never emitted or returned, because it may include implementation
  // detail that is not appropriate for an unauthenticated response or log.
  const stack = error instanceof Error ? error.stack ?? "" : "";
  const signal = `${safeErrorName(error) ?? ""} ${safeErrorCode(error) ?? ""} ${stack}`.toLowerCase();
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

function classifyDatabaseFailure(error: unknown): DatabaseFailureReason {
  const message = messageForClassification(error);
  if (/no such table|table .* does not exist|missing table/.test(message)) return "missing_table";
  if (/no such column|column .* does not exist|missing column/.test(message)) return "missing_column";
  if (/binding|unavailable|network|transport|connection/.test(message)) return "binding_or_transport";
  if (/constraint|syntax|query|prepare/.test(message)) return "query_or_constraint";
  return "other";
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
    const category = classifyUnexpectedAuthFailure(error);
    console.error("auth_handler_unexpected_error", {
      category,
      error_name: safeErrorName(error) ?? typeof error,
      error_code: safeErrorCode(error),
      database_reason: category === "database" ? classifyDatabaseFailure(error) : null,
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
