const OPS_AUTH_PREFIX = "Bearer ";
const NO_STORE_HEADERS = { "Cache-Control": "no-store" };

function resolveOpsToken(): string {
  return process.env.OPS_PROJECTION_TOKEN || process.env.OPS_ADAPTER_TOKEN || "";
}

function responsePayload(message: string, status: number) {
  return Response.json({ message }, { status, headers: NO_STORE_HEADERS });
}

export function ensureOpsAuthorization(request: Request): Response | null {
  const configuredToken = resolveOpsToken();
  if (!configuredToken.trim()) {
    return responsePayload("ops adapter secret 未配置，请设置 OPS_ADAPTER_TOKEN。", 503);
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

export function buildOpsProbePayload(adapterName: string, extras: Record<string, unknown> = {}) {
  return {
    adapter: adapterName,
    reachable: true,
    timestamp: new Date().toISOString(),
    ...extras,
  };
}

export { NO_STORE_HEADERS };
