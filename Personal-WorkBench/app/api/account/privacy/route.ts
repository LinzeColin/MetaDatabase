import { env } from "cloudflare:workers";
import { createAuth } from "@/server/auth";
import { requireVerifiedSession } from "@/server/auth/session";
import {
  ACCOUNT_PRIVACY_NOTICE_SHA256,
  ACCOUNT_PRIVACY_POLICY_VERSION,
  getPrivacyState,
  parsePrivacyInput,
  setPrivacyConsent,
} from "@/server/data/account-lifecycle";
import { apiErrorResponse, readJson } from "@/server/http/api";

export const runtime = "edge";

function currentPolicyVersion() {
  return ACCOUNT_PRIVACY_POLICY_VERSION;
}

function currentNoticeSha256() {
  return ACCOUNT_PRIVACY_NOTICE_SHA256;
}

export async function GET(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const snapshot = await getPrivacyState(env.DB, identity.userId);
    return Response.json(
      { ...snapshot, policyVersion: currentPolicyVersion(), noticeSha256: currentNoticeSha256(), currentVersion: currentPolicyVersion() },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    const identity = await requireVerifiedSession(createAuth(env), request.headers);
    const parsed = parsePrivacyInput(await readJson(request));
    if (parsed.policyVersion !== currentPolicyVersion() || parsed.noticeSha256 !== currentNoticeSha256()) {
      return Response.json(
        { message: "隐私说明版本与当前公开声明不一致，请刷新后重试。" },
        { status: 409, headers: { "Cache-Control": "no-store" } },
      );
    }
    const result = await setPrivacyConsent(env.DB, identity.userId, parsed);
    return Response.json(
      {
        state: result.privacyState,
        policyVersion: result.privacyPolicyVersion,
        decidedAt: result.decidedAt,
        currentVersion: currentPolicyVersion(),
        noticeSha256: currentNoticeSha256(),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return apiErrorResponse(error);
  }
}
