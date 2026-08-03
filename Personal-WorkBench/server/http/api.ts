import { AuthRuntimeNotReadyError } from "@/server/auth";
import {
  NotAccessibleError,
  TenantInputError,
  UnauthorizedError,
  VerificationRequiredError,
} from "@/server/security/tenant";
import { IdempotencyConflictError, IdempotencyError } from "@/server/data/idempotency";
import { ResourceInputError } from "@/server/data/resources";
import { PrivateFileInputError } from "@/server/files/private-files";

export function notFoundResponse(): Response {
  return Response.json({ message: "未找到内容。" }, { status: 404, headers: { "Cache-Control": "no-store" } });
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    throw new ResourceInputError();
  }
}

export function apiErrorResponse(error: unknown): Response {
  if (error instanceof AuthRuntimeNotReadyError) {
    return Response.json({ message: "服务暂时不可用，请稍后再试。" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
  if (error instanceof UnauthorizedError) {
    return Response.json({ message: "请先登录。" }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }
  if (error instanceof VerificationRequiredError) {
    return Response.json({ message: "请先完成邮箱验证。" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  if (error instanceof NotAccessibleError) return notFoundResponse();
  if (error instanceof IdempotencyConflictError) {
    return Response.json({ message: "请勿重复使用此操作标识。" }, { status: 409, headers: { "Cache-Control": "no-store" } });
  }
  if (
    error instanceof IdempotencyError ||
    error instanceof ResourceInputError ||
    error instanceof TenantInputError ||
    error instanceof PrivateFileInputError
  ) {
    return Response.json({ message: "填写内容有误，请检查后重试。" }, { status: 400, headers: { "Cache-Control": "no-store" } });
  }
  return Response.json({ message: "服务暂时不可用，请稍后再试。" }, { status: 500, headers: { "Cache-Control": "no-store" } });
}
