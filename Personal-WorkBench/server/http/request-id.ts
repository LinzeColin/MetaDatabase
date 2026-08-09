export const IDEMPOTENCY_QUERY_PARAM = "request_id";

/**
 * Browser writes send their random replay token in the same-origin URL rather
 * than a non-simple request header. The header remains accepted so an in-flight
 * older client can safely retry while a new version is rolling out.
 */
export function readIdempotencyKey(request: Request): string | null {
  return request.headers.get("idempotency-key") ?? new URL(request.url).searchParams.get(IDEMPOTENCY_QUERY_PARAM);
}
