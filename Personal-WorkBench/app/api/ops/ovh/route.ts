import {
  buildOpsProbePayload,
  ensureOpsAuthorization,
  NO_STORE_HEADERS,
  normalizedOpsWriteMode,
} from "@/server/security/ops";

export const runtime = "nodejs";

function writeMode() {
  return normalizedOpsWriteMode(process.env.OVH_ADAPTER_WRITE);
}

export async function GET(request: Request): Promise<Response> {
  const authResult = ensureOpsAuthorization(request);
  if (authResult) return authResult;

  return Response.json(
    buildOpsProbePayload("ovh", { writeMode: writeMode() }),
    { headers: NO_STORE_HEADERS },
  );
}
