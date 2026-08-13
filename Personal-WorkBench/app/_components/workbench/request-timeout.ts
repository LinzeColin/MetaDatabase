/**
 * Workbench controls stay usable when an otherwise valid first-party request
 * is stalled by a transient browser or network condition. Callers preserve
 * their existing fallback and idempotency behaviour after this bounded wait.
 */
export const WORKBENCH_REQUEST_TIMEOUT_MS = 8_000;

export async function requestWithTimeout(
  path: string,
  init: RequestInit,
  timeoutMs = WORKBENCH_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(path, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}
