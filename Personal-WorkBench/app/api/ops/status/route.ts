import { buildOpsProbePayload, ensureOpsAuthorization, NO_STORE_HEADERS } from "@/server/security/ops";

export const runtime = "nodejs";

function isReadOnlyMode() {
  const raw = process.env.STATUS_ADAPTER_READONLY;
  if (!raw) return true;
  return raw.trim().toLowerCase() !== "false";
}

export async function GET(request: Request): Promise<Response> {
  const authResult = ensureOpsAuthorization(request);
  if (authResult) return authResult;

  return Response.json(
    buildOpsProbePayload("status", { readOnly: isReadOnlyMode() }),
    { headers: NO_STORE_HEADERS },
  );
}
