import { AuthRuntimeNotReadyError } from "@/server/auth";
import {
  NotAccessibleError,
  ReauthenticationRequiredError,
  TenantInputError,
  UnauthorizedError,
  VerificationRequiredError,
} from "@/server/security/tenant";
import { IdempotencyConflictError, IdempotencyError } from "@/server/data/idempotency";
import { ResourceInputError } from "@/server/data/resources";
import { PrivateFileInputError } from "@/server/files/private-files";
import { AccountDeleteStateError, AccountInputError, AccountNotFoundError } from "@/server/data/account-lifecycle";
import { LegacyImportConflictError } from "@/server/data/legacy-import";
import { SensitiveCloudConsentRequiredError } from "@/server/security/privacy-consent";
import { SameOriginRequiredError } from "@/server/security/mutation-origin";

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
  if (error instanceof SameOriginRequiredError) {
    return Response.json({ message: "请求来源无效，请刷新后重试。" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  if (error instanceof ReauthenticationRequiredError) {
    return Response.json({ message: "为保护账户安全，请重新登录后再继续删除。" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  if (error instanceof SensitiveCloudConsentRequiredError) {
    return Response.json(
      { message: "请先在账户中心开启敏感内容跨设备保存。" },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (error instanceof NotAccessibleError) return notFoundResponse();
  if (error instanceof IdempotencyConflictError) {
    return Response.json({ message: "请勿重复使用此操作标识。" }, { status: 409, headers: { "Cache-Control": "no-store" } });
  }
  if (
    error instanceof LegacyImportConflictError ||
    error instanceof AccountInputError ||
    error instanceof IdempotencyError ||
    error instanceof ResourceInputError ||
    error instanceof TenantInputError ||
    error instanceof PrivateFileInputError
  ) {
    return Response.json(
      { message: error instanceof LegacyImportConflictError ? error.message : "填写内容有误，请检查后重试。" },
      {
        status: error instanceof LegacyImportConflictError ? 409 : 400,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
  if (error instanceof AccountNotFoundError || error instanceof AccountDeleteStateError) {
    return Response.json({ message: error.message }, { status: error.status, headers: { "Cache-Control": "no-store" } });
  }
  return Response.json({ message: "服务暂时不可用，请稍后再试。" }, { status: 500, headers: { "Cache-Control": "no-store" } });
}
