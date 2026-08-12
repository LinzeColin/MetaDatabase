const OPS_AUTH_PREFIX = "Bearer ";
const NO_STORE_HEADERS = { "Cache-Control": "no-store" };

export type OpsAdapterName = "status" | "ovh" | "private_database";
export type OpsWriteMode = "readonly" | "readwrite" | "unknown";

type OpsProbeExtras = {
  readOnly?: boolean;
  writeMode?: OpsWriteMode;
};

function resolveOpsToken(): string {
  return process.env.OPS_PROJECTION_TOKEN || process.env.OPS_ADAPTER_TOKEN || "";
}

function responsePayload(message: string, status: number) {
  return Response.json({ message }, { status, headers: NO_STORE_HEADERS });
}

export function ensureOpsAuthorization(request: Request): Response | null {
  const configuredToken = resolveOpsToken();
  if (!configuredToken.trim()) {
    // Configuration names and secret state are operational details. An
    // unauthenticated caller only needs a retry-safe availability result.
    return responsePayload("ops adapter 暂不可用，请稍后重试。", 503);
  }

  const authHeader = request.headers.get("authorization") || "";
  if (!authHeader.startsWith(OPS_AUTH_PREFIX)) {
    return responsePayload("missing ops adapter token", 401);
  }
  const providedToken = authHeader.slice(OPS_AUTH_PREFIX.length).trim();
  if (providedToken !== configuredToken) {
    return responsePayload("invalid ops adapter token", 401);
  }
  return null;
}

/**
 * The only facts eligible for an ops projection are a fixed adapter label,
 * reachability timestamp and the two low-sensitivity capability flags below.
 * Never spread arbitrary environment or request data into this payload.
 */
export function buildOpsProbePayload(adapterName: OpsAdapterName, extras: OpsProbeExtras = {}) {
  const capability = extras.readOnly === undefined ? {} : { readOnly: extras.readOnly };
  const writeMode = extras.writeMode === undefined ? {} : { writeMode: extras.writeMode };
  return {
    adapter: adapterName,
    reachable: true,
    timestamp: new Date().toISOString(),
    ...capability,
    ...writeMode,
  };
}

/** Do not project arbitrary runtime text into an operational status payload. */
export function normalizedOpsWriteMode(value: string | undefined): OpsWriteMode {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "readonly") return "readonly";
  if (normalized === "readwrite") return "readwrite";
  return "unknown";
}

export { NO_STORE_HEADERS };
