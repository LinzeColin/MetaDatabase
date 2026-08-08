import { buildOpsProbePayload, ensureOpsAuthorization, NO_STORE_HEADERS } from "@/server/security/ops";

export const runtime = "edge";

function writeMode() {
  const raw = process.env.OVH_ADAPTER_WRITE;
  return raw ? raw.trim().toLowerCase() : "readwrite";
}

export async function GET(request: Request): Promise<Response> {
  const authResult = ensureOpsAuthorization(request);
  if (authResult) return authResult;

  return Response.json(
    buildOpsProbePayload("ovh", { writeMode: writeMode() }),
    { headers: NO_STORE_HEADERS },
  );
}
